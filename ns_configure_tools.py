#!/usr/bin/env python3
"""
ns_configure_tools.py - INTERACTIVE Netskope dev-tools SSL configuration helper.

What it does
  1. Gets the Netskope certificate bundle:
       a) downloads the tenant Root + Intermediate with the Netskope REST API v2
          (GET /api/v2/services/certs/subordinates?purpose=tenant_ca, needs a token with read access;
          the token comes from NETSKOPE_API_TOKEN or a hidden prompt and is never saved), else
       b) lets you point to an existing bundle, or to the Root + Intermediate files and builds it.
  2. Detects which of the documented developer tools exist on this machine.
  3. Configures the ones you select to trust the bundle (manual-only tools are listed with instructions).
  4. Saves your selection to ns_tools_config.json so ns_deploy_tools.py can replay it unattended (MDM).

Portable: config and log files live next to this script. Standard library only (Python 3.8+).
"""
import argparse, getpass, json, os, re, shutil, ssl, subprocess, sys, urllib.error, urllib.request

import ns_tools_common as c

CURL_CA_URL = "https://curl.se/ca/cacert.pem"
PUBLIC_CA_MIN_BYTES = 50000          # the real cacert.pem is ~200+ KB; less means an error page, not the bundle
CERT_API_PATH = "/api/v2/services/certs/subordinates?purpose=tenant_ca"
PEM_RE = re.compile(r"-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----")
TENANT_RE = re.compile(r"[A-Za-z0-9.-]+(:\d{1,5})?")


def ask(prompt, default=None):
    suffix = " [%s]" % default if default else ""
    try:
        v = input(prompt + suffix + ": ").strip()
    except EOFError:
        v = ""
    return v or default


def yes(prompt, default=True):
    v = ask(prompt + (" (Y/n)" if default else " (y/N)"))
    if not v:
        return default
    return v.lower().startswith("y")


def read_pem(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        t = f.read().strip()
    return t + "\n"


def download(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
        return r.read().decode("utf-8", errors="ignore")


def write_bundle(netskope_pems, public_path):
    """Order matters: Intermediate, then Root (the caller passes them in that order), then public CAs."""
    parts = list(netskope_pems)
    if public_path and os.path.exists(public_path):
        parts.append(read_pem(public_path))
    else:
        try:
            c.log("Downloading public CA bundle from %s" % CURL_CA_URL)
            body = download(CURL_CA_URL)
            if len(body) < PUBLIC_CA_MIN_BYTES:
                raise ValueError("the download looks truncated (%d bytes)" % len(body))
            parts.append(body.strip() + "\n")
        except Exception as e:
            c.log("WARNING: could not download public CA bundle (%s). Bundle will contain only the Netskope certs; "
                  "bypassed sites will fail until you add cacert.pem." % e)
    with open(c.BUNDLE_LOCAL, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(parts))
    return c.BUNDLE_LOCAL


def build_bundle(root_path, inter_path, public_path):
    return write_bundle([read_pem(inter_path), read_pem(root_path)], public_path)


# ------------------------------------------------------------ REST API v2
class ApiError(Exception):
    pass


def fetch_tenant_certs(tenant, token):
    """Read the tenant's Root/Intermediate certificates with REST API v2. Returns a list of PEM strings.
    TLS verification stays ON. Only PEM CERTIFICATE blocks are taken from the response."""
    url = "https://%s%s" % (tenant, CERT_API_PATH)
    ctx = ssl.create_default_context()
    body, status = None, None
    # RBAC v3 service-account tokens use a Bearer header; classic v2 tokens use Netskope-Api-Token.
    for header, value in (("Authorization", "Bearer " + token), ("Netskope-Api-Token", token)):
        req = urllib.request.Request(url, headers={"Accept": "application/json", header: value})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            status = e.code
            if e.code in (401, 403):
                continue
            raise ApiError("the tenant answered HTTP %d" % e.code)
        except urllib.error.URLError as e:
            raise ApiError("could not connect to %s (%s)" % (tenant, e.reason))
        except OSError as e:
            raise ApiError("could not connect to %s (%s)" % (tenant, e))
    if body is None:
        raise ApiError("HTTP %s: the token was rejected. It needs read access to "
                       "/api/v2/services/certs/subordinates." % status)
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        raise ApiError("the response was not JSON")
    items = data.get("certificates") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        seen = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise ApiError("no certificates in the response (top-level fields: %s)" % (seen,))
    pems = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("certificate", "issuer"):
            value = item.get(key)
            if isinstance(value, str):
                for block in PEM_RE.findall(value):
                    pem = block.strip() + "\n"
                    if pem not in pems:
                        pems.append(pem)
    if not pems:
        fields = sorted(items[0]) if isinstance(items[0], dict) else []
        raise ApiError("the response had no PEM certificates (fields seen: %s)" % (fields,))
    return pems


def cert_names(pem):
    """(subject, issuer) of a PEM certificate using openssl, or None when openssl is unavailable."""
    if not shutil.which("openssl"):
        return None
    try:
        r = subprocess.run(["openssl", "x509", "-noout", "-subject", "-issuer", "-nameopt", "RFC2253"],
                           input=pem, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    subject = issuer = None
    for line in r.stdout.splitlines():
        if line.startswith("subject="):
            subject = line[len("subject="):].strip()
        elif line.startswith("issuer="):
            issuer = line[len("issuer="):].strip()
    return (subject, issuer) if subject and issuer else None


def order_intermediate_first(pems):
    """The bundle must start with the Intermediate and then the Root. Returns (pems, note)."""
    if len(pems) != 2:
        return pems, "%d certificates returned: kept in the order the API gave them" % len(pems)
    a, b = cert_names(pems[0]), cert_names(pems[1])
    if not a or not b:
        return pems, "could not check the Intermediate -> Root order (openssl not found)"
    if a[1] == b[0] and a[0] != a[1]:
        return pems, None
    if b[1] == a[0] and b[0] != b[1]:
        return [pems[1], pems[0]], "swapped into Intermediate -> Root order"
    return pems, "WARNING: the two certificates do not look like an Intermediate -> Root pair"


def bundle_from_api(tenant, token, public_path):
    pems = fetch_tenant_certs(tenant, token)
    pems, note = order_intermediate_first(pems)
    c.log("Downloaded %d Netskope certificate(s) from %s%s" % (len(pems), tenant, " (%s)" % note if note else ""))
    return write_bundle(pems, public_path)


def clean_tenant(value):
    """Accept 'tenant.goskope.com' or a pasted URL; return the bare host[:port] or None."""
    if not value:
        return None
    value = re.sub(r"^https?://", "", value.strip(), flags=re.I).split("/")[0].strip()
    return value if value and TENANT_RE.fullmatch(value) else None


def try_api_download(args, cfg):
    """Returns (bundle_path, tenant) or (None, None). The token is read from the environment or a hidden
    prompt, kept only in memory, and never written to the config, the log or the screen."""
    tenant = clean_tenant(args.tenant or os.environ.get("NETSKOPE_TENANT") or cfg.get("tenant"))
    token = os.environ.get("NETSKOPE_API_TOKEN")
    if not args.tenant and not token:
        if not yes("Download the Root + Intermediate from your tenant with an API v2 token?", True):
            return None, None
    if not tenant:
        tenant = clean_tenant(ask("Tenant host name (for example mytenant.eu.goskope.com)"))
    if not tenant:
        print("No valid tenant host name, skipping the API download.")
        return None, None
    if not token:
        try:
            token = getpass.getpass("API v2 token (input hidden, not saved): ").strip()
        except (EOFError, KeyboardInterrupt):
            token = ""
    if not token:
        print("No token given, skipping the API download.")
        return None, None
    try:
        return bundle_from_api(tenant, token, None), tenant
    except ApiError as e:
        c.log("API download failed: %s" % e)
    except Exception as e:
        c.log("API download failed: %s" % type(e).__name__)
    return None, None


def obtain_bundle(args, cfg):
    """Returns (bundle_path, tenant_or_None)."""
    # 1. explicit existing bundle
    if args.bundle:
        return args.bundle, None
    # 2. already sitting next to the script
    if os.path.exists(c.BUNDLE_LOCAL) and yes("Found %s next to the script. Use it?" % c.BUNDLE_NAME):
        return c.BUNDLE_LOCAL, None
    # 3. download with the Netskope REST API v2
    path, tenant = try_api_download(args, cfg)
    if path:
        return path, tenant
    # 4. ask the user
    print("\nDownload the certificates from your tenant by hand:")
    print("  Settings > Manage > Certificates > Signing CA > download Root and Intermediate\n")
    p = ask("Path to a ready bundle (.pem), or press Enter to build one from Root + Intermediate")
    if p:
        return p, None
    root = ask("Path to the Root certificate (.pem)")
    inter = ask("Path to the Intermediate certificate (.pem)")
    if not root or not inter or not os.path.exists(root) or not os.path.exists(inter):
        sys.exit("Root and Intermediate files are required.")
    return build_bundle(root, inter, ask("Path to cacert.pem (Enter to download from curl.se)")), None


def main():
    ap = argparse.ArgumentParser(description="Interactive Netskope dev-tools SSL configurator")
    ap.add_argument("--bundle", help="path to an existing netskope-cert-bundle.pem")
    ap.add_argument("--tenant", help="tenant host name for the API download, e.g. mytenant.eu.goskope.com "
                                     "(the token is read from NETSKOPE_API_TOKEN or asked, hidden, never saved)")
    ap.add_argument("--all", action="store_true", help="configure every detected tool without asking per tool")
    ap.add_argument("--dry-run", action="store_true", help="show what would be done, change nothing")
    args = ap.parse_args()

    cfg = {}
    if os.path.exists(c.CONFIG_FILE):
        try:
            cfg = json.load(open(c.CONFIG_FILE, encoding="utf-8"))
        except Exception:
            cfg = {}

    c.log("== Netskope dev-tools SSL configurator (%s) ==" % c.OS)
    src, tenant = obtain_bundle(args, cfg)
    if not os.path.exists(src):
        sys.exit("Bundle not found: %s" % src)
    n = c.count_certs(src)
    if n < 3:
        print("WARNING: bundle contains only %d certificate(s). Expected the Netskope Root + Intermediate plus the public CAs." % n)
        if not yes("Continue anyway?", False):
            sys.exit(1)
    print("Bundle OK: %d certificates" % n)

    # detect
    tools = c.tools_for_this_os()
    found = [t for t in tools if c.detect(t)]
    manual_always = [t for t in tools if t["method"] == "manual" and not t.get("exes")]
    print("\nDetected %d of %d documented tool groups on this machine:" % (len(found), len(tools)))
    for t in found:
        print("  - %s  [%s]" % (t["name"], t["method"]))

    if not found:
        print("Nothing detected on PATH.")

    selected = []
    for t in found:
        if args.all or yes("Configure %s?" % t["name"]):
            selected.append(t)

    # install bundle to the standard Netskope location
    installed = src if args.dry_run else c.install_bundle(src)
    print("\nBundle location used for configuration: %s" % installed)

    results = []
    for t in selected:
        if args.dry_run:
            st, d = "dry-run", t["method"]
        else:
            st, d = c.apply_tool(t, installed)
        c.log("[%s] %s - %s" % (st.upper(), t["name"], d))
        results.append(dict(name=t["name"], status=st))
        if t.get("needs_root") and st == "fail":
            print("   (this step may need administrator/root rights)")

    # manual-only tools that cannot be detected
    print("\nTools that need manual steps (cannot be automated or detected):")
    for t in manual_always:
        print("  - %s: %s" % (t["name"], t.get("note", "")))

    # save selection for the MDM script
    out = dict(
        version=1, os=c.OS,
        tenant=tenant or clean_tenant(cfg.get("tenant")) or "",   # host name only, never a token
        selected=[t["name"] for t in selected],
    )
    if not args.dry_run:
        json.dump(out, open(c.CONFIG_FILE, "w", encoding="utf-8"), indent=2)
        print("\nSaved selection to %s" % c.CONFIG_FILE)
        print("Ship ns_deploy_tools.py + ns_tools_common.py + this JSON + your bundle to deploy via MDM.")
    ok = sum(1 for r in results if r["status"] == "ok")
    print("Done: %d configured, %d failed." % (ok, sum(1 for r in results if r["status"] == "fail")))
    if c.OS != "win":
        print("Open a new terminal (or run 'source ~/.zshrc' / '~/.bashrc') for env vars to take effect.")
    else:
        print("Open a new terminal for the new environment variables to take effect.")


if __name__ == "__main__":
    main()
