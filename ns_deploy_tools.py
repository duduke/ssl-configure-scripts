#!/usr/bin/env python3
"""
ns_deploy_tools.py - UNATTENDED deployment for MDM.

No prompts, no scanning, no downloading, no bundle building.
  * Bundle: --bundle PATH, or netskope-cert-bundle.pem sitting next to this script.
  * Tools : exactly the ones saved in ns_tools_config.json by ns_configure_tools.py.

Exit codes:  0 = all applied   1 = some tools failed   2 = bundle/config problem
Log: ns_tools.log next to this script. Standard library only.
"""
import argparse, json, os, sys

import ns_tools_common as c


def main():
    ap = argparse.ArgumentParser(description="Unattended Netskope dev-tools SSL deployment")
    ap.add_argument("--bundle", help="path to netskope-cert-bundle.pem (default: next to this script)")
    ap.add_argument("--config", default=c.CONFIG_FILE, help="config written by ns_configure_tools.py")
    args = ap.parse_args()

    src = args.bundle or c.BUNDLE_LOCAL
    if not os.path.exists(src):
        c.log("ERROR: bundle not found: %s" % src, quiet=True)
        return 2
    if c.count_certs(src) < 3:
        c.log("ERROR: bundle has fewer than 3 certificates: %s" % src, quiet=True)
        return 2
    if not os.path.exists(args.config):
        c.log("ERROR: config not found: %s (run ns_configure_tools.py first)" % args.config, quiet=True)
        return 2
    try:
        cfg = json.load(open(args.config, encoding="utf-8"))
    except Exception as e:
        c.log("ERROR: cannot read config: %s" % e, quiet=True)
        return 2
    if cfg.get("os") and cfg["os"] != c.OS:
        c.log("ERROR: config was created on '%s' but this machine is '%s'" % (cfg["os"], c.OS), quiet=True)
        return 2

    wanted = set(cfg.get("selected", []))
    by_name = {t["name"]: t for t in c.tools_for_this_os()}
    installed = c.install_bundle(src)
    c.log("Deploying %d tool(s) using bundle %s" % (len(wanted), installed), quiet=True)

    failed = 0
    for name in sorted(wanted):
        t = by_name.get(name)
        if not t:
            c.log("[SKIP] %s - not defined for this OS" % name, quiet=True)
            continue
        st, d = c.apply_tool(t, installed)
        c.log("[%s] %s - %s" % (st.upper(), name, d), quiet=True)
        if st == "fail":
            failed += 1
    c.log("Finished: %d failure(s)" % failed, quiet=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
