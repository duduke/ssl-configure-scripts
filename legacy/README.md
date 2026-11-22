# Legacy scripts (obsolete)

These scripts download the certificates from `https://addon-<tenant>/config/ca/cert?orgkey=<orgkey>` and
`.../config/org/cert?orgkey=<orgkey>` with TLS verification disabled. That method fails ("Method Not Allowed") on
tenants that use Secure Configuration / Secure Enrollment, and it should not be used.

They are kept only for reference. Use `ns_configure_tools.py` / `ns_deploy_tools.py` in the repository root.
