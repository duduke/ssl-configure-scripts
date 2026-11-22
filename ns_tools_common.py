"""
ns_tools_common.py - shared definitions for the Netskope dev-tools SSL helper.

Each tool entry describes:
  detect   : how to find the tool (executable name(s) and/or filesystem paths)
  method   : how to configure it
               env      -> set an environment variable to the bundle path
               cmd      -> run a command that takes the bundle path
               node_sysca -> sets NODE_USE_SYSTEM_CA=1, only if the installed Node supports it
               yarn     -> version-aware (Yarn Classic: cafile, Yarn Berry: httpsCaFilePath)
               hgrc     -> writes [web] cacerts into the user's Mercurial config
               manual   -> cannot be automated, show instructions
               os_store -> relies on the OS certificate store (no action here)
               depends  -> covered by another tool's configuration
  platforms: which OSes the entry applies to (win / mac / linux)

Based on the "SSL Inspection - Development Tools / CLI Tools" Confluence article.
"""
import json, os, platform, shutil, subprocess, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv and sys.argv[0] else __file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "ns_tools_config.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "ns_tools.log")
BUNDLE_NAME = "netskope-cert-bundle.pem"
BUNDLE_LOCAL = os.path.join(SCRIPT_DIR, BUNDLE_NAME)


def current_os():
    s = platform.system().lower()
    if s.startswith("win"):
        return "win"
    if s == "darwin":
        return "mac"
    return "linux"


OS = current_os()


def default_bundle_dir():
    """Where the bundle is installed on this machine (same paths as the article).
    Set NS_BUNDLE_DIR to override (useful for testing or custom layouts)."""
    if os.environ.get("NS_BUNDLE_DIR"):
        return os.environ["NS_BUNDLE_DIR"]
    if OS == "win":
        return r"C:\ProgramData\Netskope\STAgent\download"
    if OS == "mac":
        return "/Library/Application Support/Netskope/STAgent/data"
    return "/opt/netskope"


ALL = ("win", "mac", "linux")

# name, detect(exes, paths), method, extra, platforms
TOOLS = [
    # ---- environment-variable based tools ----
    dict(name="OpenSSL / Ruby / Go / GLab / svn / Fastlane", exes=["openssl", "ruby", "go", "glab", "svn", "fastlane"],
         method="env", var="SSL_CERT_FILE", platforms=ALL),
    dict(name="cURL / Yum / pip (libcurl)", exes=["curl"], method="env", var="SSL_CERT_FILE", platforms=("mac", "linux"),
         note="Shares SSL_CERT_FILE with OpenSSL"),
    dict(name="cURL (Windows)", exes=["curl"], method="curlrc", platforms=("win",)),
    dict(name="Git", exes=["git"], method="env", var="GIT_SSL_CAINFO", platforms=ALL,
         note="On Windows with Git > 2.14 you can instead run: git config --global http.sslbackend schannel"),
    dict(name="Python Requests / Azure CLI / pip / oci-cli / OpenAI(py)", exes=["python", "python3", "pip", "pip3", "az", "oci"],
         method="env", var="REQUESTS_CA_BUNDLE", platforms=ALL,
         note="Python 3.13+ enables strict X.509 checks; an older tenant CA without Authority Key Identifier fails with 'Missing Authority Key Identifier' even with the bundle set"),
    dict(name="AWS CLI / Boto3", exes=["aws"], method="env", var="AWS_CA_BUNDLE", platforms=ALL),
    dict(name="NodeJS / Amplify / Heroku / SFDX / Shopify / OpenAI(node)", exes=["node", "amplify", "heroku", "sfdx", "sf", "shopify"],
         method="env", var="NODE_EXTRA_CA_CERTS", platforms=ALL,
         note="Works on every Node version. See the next entry for the optional OS-store setting"),
    dict(name="NodeJS - use OS certificate store (optional, newer Node only)", exes=["node"], method="node_sysca", platforms=ALL,
         note="Sets NODE_USE_SYSTEM_CA=1 on Node 22.19+ / 24.6+ (in addition to NODE_EXTRA_CA_CERTS). Needs the Netskope cert in the OS store; older Node ignores it"),
    # ---- tools configured through their own CLI ----
    dict(name="gcloud CLI", exes=["gcloud"], method="cmd",
         cmd=["gcloud", "config", "set", "core/custom_ca_certs_file", "{bundle}"], platforms=ALL),
    dict(name="npm / pnpm / Shopify", exes=["npm", "pnpm"], method="cmd",
         cmd=["npm", "config", "set", "cafile", "{bundle}"], platforms=ALL),
    dict(name="Yarn (Classic 1.x: cafile / Berry 2+: httpsCaFilePath)", exes=["yarn"], method="yarn", platforms=ALL,
         note="Version-dependent. Berry stores the setting in .yarnrc.yml; NODE_EXTRA_CA_CERTS (NodeJS entry) is also needed there"),
    dict(name="Composer", exes=["composer"], method="cmd",
         cmd=["composer", "config", "--global", "cafile", "{bundle}"], platforms=ALL,
         note="Alternative: openssl.cafile in php.ini"),
    dict(name="Conda", exes=["conda"], method="cmd",
         cmd=["conda", "config", "--set", "ssl_verify", "{bundle}"], platforms=ALL,
         note="Points ssl_verify at the bundle (must contain root + intermediate). Alternative: 'ssl_verify truststore' needs Conda >= 23.9 and Python >= 3.10"),
    dict(name="Ubuntu Livepatch", exes=["canonical-livepatch"], method="cmd",
         cmd=["canonical-livepatch", "config", "ca-certs={bundle}"], platforms=("linux",), needs_root=True),
    # ---- Java keystore based ----
    dict(name="Java (keystore import)", exes=["keytool"], method="keytool", platforms=ALL, needs_root=True,
         note="Imports the bundle into $JAVA_HOME cacerts. Covers Gradle and Maven."),
    dict(name="Maven (OS trust store alternative)", exes=["mvn"], method="manual", platforms=ALL,
         note="Use -Djavax.net.ssl.trustStoreType (Windows-ROOT / KeychainStore) in MAVEN_OPTS - NOT keyStoreType. Windows-ROOT only sees the current user store; JDK 19+ adds Windows-ROOT-LOCALMACHINE"),
    # ---- OS certificate store ----
    dict(name="Linux OS store (Zypper, VMs)", exes=["update-ca-certificates", "update-ca-trust"], method="linux_store",
         platforms=("linux",), needs_root=True),
    # ---- tools that rely on the OS store (informational) ----
    dict(name="Volta", exes=["volta"], method="depends", platforms=ALL,
         note="OS-store support is unreliable (open Volta issue: not all system certs are used). Covered by NODE_EXTRA_CA_CERTS from the NodeJS entry"),
    dict(name="NuGet (Windows)", exes=["nuget", "dotnet"], method="os_store", platforms=("win",),
         note="Netskope client installs the cert in the Windows store"),
    dict(name="NuGet (Linux/Mac)", exes=["nuget", "dotnet"], method="linux_store_hint", platforms=("mac", "linux"),
         note="Unconfirmed: NuGet has no SSL_CERT_FILE support (open request); installing the cert into the OS store is the practical fix (see Linux OS store entry)"),
    dict(name="Visual Studio Code", exes=["code"], method="os_store", platforms=ALL,
         note="Embedded Chromium uses the OS store; embedded git uses the Git setting"),
    dict(name="Mercurial", exes=["hg"], method="hgrc", platforms=ALL,
         note="Mercurial does NOT use the OS store on any platform; sets [web] cacerts in the user hgrc"),
    # ---- special cases ----
    dict(name="WinGet", exes=["winget"], method="winget", platforms=("win",), needs_root=True),
    dict(name="Cargo (Rust)", exes=["cargo"], method="env", var="CARGO_HTTP_CAINFO", platforms=ALL,
         note="Uses CARGO_HTTP_CAINFO; also needs the Git setting"),
    dict(name="SwiftPM", exes=["swift", "xcodebuild"], method="manual", platforms=("mac",),
         note="Run: xcodebuild -resolvePackageDependencies -scmProvider system (Xcode < 12.5)"),
    # ---- manual / GUI ----
    dict(name="JetBrains IDEs", exes=[], method="manual", platforms=ALL,
         note="Settings > Tools > Server Certificates: import the Netskope Root and Intermediate files (not the old nscacert/nstenantcert names). Only covers the IDE's own connections; Gradle/Maven need the JDK keystore too. On Windows also enable Advanced Settings > Use Windows certificate store for Git"),
    dict(name="Azure Storage Explorer", exes=[], method="manual", platforms=ALL,
         note="Edit > SSL Certificates > Import Certificates: import ALL chain certs (root + intermediate). Known bug: ignored when proxy source is 'System proxy'"),
    dict(name="Android Studio", exes=[], method="manual", platforms=("win", "mac"),
         note="keytool -import the Netskope Root and Intermediate as SEPARATE files with different aliases into the bundled JBR cacerts (default password: changeit). Not verified"),
    dict(name="Kubernetes (kubectl)", exes=["kubectl"], method="manual", platforms=ALL,
         note="No clean fix. Use --insecure-skip-tls-verify or a Certificate Pinned App + steering exception"),
    dict(name="Docker", exes=["docker"], method="manual", platforms=ALL,
         note="Install the certs in the OS store of the Docker host (see Stefano Artioli's guide)"),
    dict(name="Cursor", exes=["cursor"], method="manual", platforms=ALL,
         note="Cursor docs: set NODE_EXTRA_CA_CERTS (done via NodeJS entry). If streaming still fails, set Settings > Network > HTTP Compatibility Mode = HTTP/1.1 (cursor.general.disableHttp2)"),
    dict(name="GitHub Copilot", exes=[], method="manual", platforms=ALL,
         note="Per current GitHub docs Copilot reads the OS trust store (win-ca / mac-ca / OpenSSL paths on Linux) and NODE_EXTRA_CA_CERTS. Verify against the Business/Individual statement in the article"),
    dict(name="Arduino IDE", exes=[], method="manual", platforms=("win",),
         note="Arduino IDE 1.x ONLY: add trustStore options to arduino.l4j.ini. No documented method exists for IDE 2.x"),
    dict(name="Snowflake ODBC", exes=[], method="manual", platforms=("win",),
         note=r"Windows: copy the bundle over the PEM in C:\Program Files\Snowflake ODBC Driver\etc. Linux 3.x: CABundleFile in simba.snowflake.ini. 4.x driver uses sf.odbc.ini"),
]


# ---------------------------------------------------------------- logging
def log(msg, quiet=False):
    line = msg
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if not quiet:
        print(line)


# ------------------------------------------------------------ bundle utils
def count_certs(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().count("BEGIN CERTIFICATE")
    except OSError:
        return 0


def install_bundle(src):
    """Copy the bundle to the standard Netskope location (falls back to next to the script)."""
    dest_dir = default_bundle_dir()
    try:
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, BUNDLE_NAME)
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copyfile(src, dest)
        return dest
    except (OSError, PermissionError):
        return os.path.abspath(src)


# ----------------------------------------------------------------- setters
def set_env(var, value):
    """Persistently set an environment variable for the current user (or machine if admin)."""
    os.environ[var] = value
    if OS == "win":
        r = subprocess.run(["setx", var, value], capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    # mac / linux: append to a managed block in the shell profile
    marker_start, marker_end = "# >>> netskope-dev-tools >>>", "# <<< netskope-dev-tools <<<"
    profiles = [os.path.expanduser("~/.zshrc")] if OS == "mac" else [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.zshrc")]
    ok = False
    for prof in profiles:
        if OS == "linux" and prof.endswith(".zshrc") and not os.path.exists(prof):
            continue
        try:
            text = open(prof, "r", encoding="utf-8").read() if os.path.exists(prof) else ""
            block = ""
            if marker_start in text:
                pre, rest = text.split(marker_start, 1)
                body, post = rest.split(marker_end, 1) if marker_end in rest else (rest, "")
                lines = [l for l in body.strip().splitlines() if not l.startswith("export %s=" % var)]
                lines.append('export %s="%s"' % (var, value))
                block = marker_start + "\n" + "\n".join(lines) + "\n" + marker_end
                text = pre + block + post
            else:
                block = "\n" + marker_start + "\n" + 'export %s="%s"' % (var, value) + "\n" + marker_end + "\n"
                text += block
            open(prof, "w", encoding="utf-8").write(text)
            ok = True
        except OSError as e:
            return False, str(e)
    return ok, "profile updated"


def run_cmd(cmd, bundle):
    cmd = [c.replace("{bundle}", bundle) for c in cmd]
    if not shutil.which(cmd[0]):
        return False, "%s not found" % cmd[0]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def write_curlrc():
    path = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".curlrc")
    try:
        existing = open(path).read() if os.path.exists(path) else ""
        add = ""
        for line in ("--ca-native", "--ssl-revoke-best-effort"):
            if line not in existing:
                add += line + "\n"
        if add:
            with open(path, "a") as f:
                f.write(add)
        return True, path
    except OSError as e:
        return False, str(e)


def split_pem(path, limit=None):
    """Return a list of individual PEM certificate blocks from a bundle."""
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    blocks, cur, inside = [], [], False
    for line in text.splitlines():
        if "BEGIN CERTIFICATE" in line:
            inside, cur = True, [line]
        elif inside:
            cur.append(line)
            if "END CERTIFICATE" in line:
                blocks.append("\n".join(cur) + "\n")
                inside = False
                if limit and len(blocks) >= limit:
                    break
    return blocks


def java_import(bundle):
    """keytool imports a single certificate per call, so import only the Netskope
    Intermediate and Root (the first two certificates in the bundle), not the whole file."""
    java_home = os.environ.get("JAVA_HOME")
    keytool = shutil.which("keytool") or (os.path.join(java_home, "bin", "keytool") if java_home else None)
    if not keytool:
        return False, "keytool not found"
    # -cacerts (Java 9+) targets the default keystore; fall back to JAVA_HOME path
    base = [keytool, "-import", "-noprompt", "-trustcacerts", "-storepass", "changeit"]
    if java_home and os.path.exists(os.path.join(java_home, "lib", "security", "cacerts")):
        base += ["-keystore", os.path.join(java_home, "lib", "security", "cacerts")]
    else:
        base += ["-cacerts"]
    certs = split_pem(bundle, limit=2)
    if len(certs) < 2:
        return False, "bundle has fewer than 2 certificates"
    import tempfile
    msgs, ok_all = [], True
    for alias, pem in zip(("netskope-intermediate", "netskope-root"), certs):
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as tf:
            tf.write(pem)
            tmp = tf.name
        try:
            r = subprocess.run(base + ["-alias", alias, "-file", tmp], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
            already = "already exists" in out
            if r.returncode != 0 and not already:
                ok_all = False
            msgs.append("%s: %s" % (alias, "already present" if already else ("ok" if r.returncode == 0 else out[-120:])))
        finally:
            os.unlink(tmp)
    return ok_all, "; ".join(msgs)


def linux_store_install(bundle):
    if shutil.which("update-ca-certificates"):
        dest = "/usr/local/share/ca-certificates/netskope-cert-bundle.crt"
        cmd = ["update-ca-certificates"]
    elif shutil.which("update-ca-trust"):
        dest = "/etc/pki/ca-trust/source/anchors/netskope-cert-bundle.pem"
        cmd = ["update-ca-trust"]
    else:
        return False, "no update-ca tool found"
    try:
        shutil.copyfile(bundle, dest)
        os.chmod(dest, 0o644)
    except (OSError, PermissionError) as e:
        return False, "need root: %s" % e
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def winget_bypass():
    """Preferred: the supported winget admin setting. Fallback: the group-policy registry value."""
    if shutil.which("winget"):
        r = subprocess.run(["winget", "settings", "--enable", "BypassCertificatePinningForMicrosoftStore"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return True, "winget admin setting enabled"
    r = subprocess.run(["reg", "add", r"HKLM\Software\Policies\Microsoft\Windows\AppInstaller",
                        "/v", "EnableBypassCertificatePinningForMicrosoftStore", "/t", "REG_DWORD", "/d", "1", "/f"],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()



def yarn_major():
    """Return the major version of the installed yarn, or None."""
    try:
        r = subprocess.run(["yarn", "--version"], capture_output=True, text=True, timeout=30)
        return int(r.stdout.strip().split(".")[0])
    except Exception:
        return None


def yarn_configure(bundle):
    """Yarn Classic (1.x) uses 'cafile'; Yarn Berry (2+) uses 'httpsCaFilePath'."""
    major = yarn_major()
    if major is None:
        return False, "could not determine yarn version"
    key = "cafile" if major < 2 else "httpsCaFilePath"
    cmd = ["yarn", "config", "set", key, bundle]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    detail = "yarn %d: set %s" % (major, key)
    if major >= 2:
        detail += " (also relies on NODE_EXTRA_CA_CERTS)"
    return r.returncode == 0, detail + (" - " + (r.stdout + r.stderr).strip() if r.returncode else "")


def hgrc_configure(bundle):
    """Mercurial reads web.cacerts from hgrc on every OS (it ignores the OS store)."""
    if OS == "win":
        path = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "mercurial.ini")
    else:
        path = os.path.expanduser("~/.hgrc")
    try:
        text = open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""
        lines = text.splitlines()
        out, in_web, done = [], False, False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                if in_web and not done:
                    out.append("cacerts = %s" % bundle)
                    done = True
                in_web = stripped.lower() == "[web]"
            elif in_web and stripped.lower().startswith("cacerts"):
                line = "cacerts = %s" % bundle
                done = True
            out.append(line)
        if in_web and not done:
            out.append("cacerts = %s" % bundle)
            done = True
        if not done:
            out += ["", "[web]", "cacerts = %s" % bundle]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        return True, "web.cacerts set in %s" % path
    except OSError as e:
        return False, str(e)


def node_version():
    """Return (major, minor) of the installed Node.js, or None."""
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=30)
        parts = r.stdout.strip().lstrip("v").split(".")
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def node_supports_system_ca_env(ver):
    """NODE_USE_SYSTEM_CA documented from 22.19 (22.x line) and 24.6 (24.x line); any newer major also has it."""
    if ver is None:
        return False
    major, minor = ver
    if major == 22:
        return minor >= 19
    if major == 24:
        return minor >= 6
    return major > 24


def node_sysca_configure(bundle):
    ver = node_version()
    if ver is None:
        return False, "could not determine Node.js version"
    label = "%d.%d" % ver
    if not node_supports_system_ca_env(ver):
        return True, "skipped: Node %s does not support NODE_USE_SYSTEM_CA (needs 22.19+ or 24.6+); NODE_EXTRA_CA_CERTS still applies" % label
    ok, d = set_env("NODE_USE_SYSTEM_CA", "1")
    return ok, "Node %s: NODE_USE_SYSTEM_CA=1 (%s)" % (label, d)

# ------------------------------------------------------------- dispatcher
def apply_tool(tool, bundle):
    """Apply one tool entry. Returns (status, detail). status: ok / fail / manual / info"""
    m = tool["method"]
    if m == "env":
        ok, d = set_env(tool["var"], bundle)
    elif m == "cmd":
        ok, d = run_cmd(tool["cmd"], bundle)
    elif m == "curlrc":
        ok, d = write_curlrc()
    elif m == "keytool":
        ok, d = java_import(bundle)
    elif m == "linux_store":
        ok, d = linux_store_install(bundle)
    elif m == "winget":
        ok, d = winget_bypass()
    elif m == "node_sysca":
        ok, d = node_sysca_configure(bundle)
    elif m == "yarn":
        ok, d = yarn_configure(bundle)
    elif m == "hgrc":
        ok, d = hgrc_configure(bundle)
    elif m in ("depends", "linux_store_hint"):
        return "info", tool.get("note", "")
    elif m == "manual":
        return "manual", tool.get("note", "")
    elif m == "os_store":
        return "info", tool.get("note", "Uses the OS certificate store")
    else:
        return "fail", "unknown method %s" % m
    return ("ok" if ok else "fail"), d


def tools_for_this_os():
    return [t for t in TOOLS if OS in t["platforms"]]


def detect(tool):
    """True if any of the tool's executables is on PATH."""
    return any(shutil.which(e) for e in tool.get("exes", []))
