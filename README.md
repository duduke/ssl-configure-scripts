# ssl-configure-scripts

Scripts for Linux, macOS and Windows that detect popular CLI tools, libraries and frameworks on a device that goes
through SSL inspection (MITM), and configure them to trust the Netskope certificate bundle.

## Repository layout
| Path | Purpose |
|------|---------|
| `ns_configure_tools.py` | Interactive. Gets the bundle, detects tools, configures the ones you pick, saves `ns_tools_config.json`. |
| `ns_deploy_tools.py` | Unattended, for MDM. No prompts, no scanning, no downloading. Replays the saved config. |
| `ns_tools_common.py` | Shared tool definitions and helpers. Must sit next to both scripts. |

Configures developer tools (git, npm, pip, AWS CLI, gcloud, Java, ...) to trust the Netskope SSL-inspection
certificate bundle. Standard library only, Python 3.8+. Windows, macOS, Linux.

## Quick start
    export NETSKOPE_API_TOKEN=<token with read access to /api/v2/services/certs/subordinates>
    python ns_configure_tools.py --tenant mytenant.eu.goskope.com

No token? Run `python ns_configure_tools.py` and point it at the Root and Intermediate certificates you downloaded
from **Settings > Manage > Certificates > Signing CA**. Details below.

Config (`ns_tools_config.json`) and log (`ns_tools.log`) are written next to the scripts, so the folder is portable.

## 1. Interactive run (once, on a reference machine)
1. Run `python ns_configure_tools.py`.
2. Get the bundle in one of two ways:
   * **Automatic (API v2).** Give your tenant host name and an API v2 token. The script downloads the tenant
     Root + Intermediate and builds the bundle (order: Intermediate, Root, then the public CAs from curl.se).
   * **Manual.** In your tenant go to **Settings > Manage > Certificates > Signing CA**, download the **Root** and
     **Intermediate**, and point the script at them (or at a ready bundle).
3. Pick the tools to configure. Your selection is saved to `ns_tools_config.json`.

Options: `--bundle PATH`, `--tenant HOST`, `--all` (no per-tool questions), `--dry-run` (change nothing).

### API download
    set NETSKOPE_API_TOKEN=<token>           (Windows)      export NETSKOPE_API_TOKEN=<token>   (macOS/Linux)
    python ns_configure_tools.py --tenant mytenant.eu.goskope.com

* Endpoint: `GET https://<tenant>/api/v2/services/certs/subordinates?purpose=tenant_ca`. **It is not in Netskope's
  public documentation.** It was taken from a community script (ns-toconnor/ssl-configure-script), so confirm it
  with Netskope before relying on it.
* The token needs read access to `/api/v2/services/certs/subordinates`. A Bearer header is tried first, then the
  `Netskope-Api-Token` header.
* The token is read from `NETSKOPE_API_TOKEN` or a hidden prompt. It is never written to the config, the log or the
  screen. Only the tenant host name is saved in `ns_tools_config.json`.
* TLS verification is always on. If the call fails (bad token, wrong scope, network), the script says why and falls
  back to the manual steps.
* `ns_deploy_tools.py` never downloads anything. Ship it the finished bundle.

## 2. MDM deployment
Ship one folder containing `ns_deploy_tools.py`, `ns_tools_common.py`, `ns_tools_config.json`
and `netskope-cert-bundle.pem`, then run:

    python ns_deploy_tools.py                     # bundle next to the script
    python ns_deploy_tools.py --bundle <path>     # or pass the bundle path

Exit codes: `0` all applied, `1` some tools failed, `2` bundle or config problem.

## Tool-specific behaviour (verified against current vendor docs, Nov 2026)
* **Yarn** is version-aware. Classic (1.x) gets `cafile`, Berry (2+) gets `httpsCaFilePath`. Berry also needs
  `NODE_EXTRA_CA_CERTS`, which the NodeJS entry sets.
* **Mercurial** does not use the OS certificate store on any platform. The script writes `[web] cacerts = <bundle>`
  to `~/.hgrc` (Windows: `%USERPROFILE%\mercurial.ini`). Existing settings are preserved and re-runs do not duplicate the line.
* **Conda** gets `ssl_verify` pointed at the bundle (it must contain root + intermediate).
  The alternative `ssl_verify truststore` needs Conda 23.9+ and Python 3.10+.
* **NodeJS** gets two settings. `NODE_EXTRA_CA_CERTS` (the bundle) is always set and works on every Node version.
  On top of that, `NODE_USE_SYSTEM_CA=1` is set only when the installed Node is 22.19+ or 24.6+; on older Node it is
  skipped with a log message, because older versions silently ignore it. The check runs on each machine, so one saved
  config can be deployed to machines with different Node versions. Node 23.x is deliberately skipped (no source
  confirms the variable there). The OS-store setting only helps if the Netskope certificate is in the OS store,
  and tools that bundle their own Node or set their own CA list may ignore it.
* **Volta** is treated as covered by `NODE_EXTRA_CA_CERTS`. Its OS-store support is unreliable (open Volta issue).
* **Java keytool** imports only the Netskope Intermediate and Root, as two separate aliases, never the whole bundle.
* **Git** uses `GIT_SSL_CAINFO` (a file), not `GIT_SSL_CAPATH` (a directory).
* **Python 3.13+**: an older tenant CA without an Authority Key Identifier fails strict verification even with the
  bundle set. Use a newer tenant CA or bypass the affected domains.
* **Informational only (no automatic change):** NuGet on Linux/Mac (unconfirmed, OS store is the practical fix),
  Arduino IDE (1.x only, no known method for 2.x), Snowflake ODBC (3.x vs 4.x config files differ),
  JetBrains (IDE-only scope), Azure Storage Explorer (import all chain certs).
* Not verified against vendor docs, so no automatic change is made: Docker, SwiftPM, Gradle, Kubernetes, Sourcetree, svn,
  GitLab CLI, Fastlane, Heroku CLI, Amplify, Oracle Cloud CLI, OpenAI API, Zypper, Yum, Ruby, Go, Shopify CLI and PNPM.
  Android Studio's default keystore password (`changeit`) should be checked on your machine.

## Notes
* The config is OS-specific. Create one per OS. The deploy script refuses a config from another OS.
* Some steps need admin/root (Java keystore, Linux OS store, WinGet). Run the MDM job with those rights.
* Environment variables apply to **new** terminals only.
* Tools that cannot be automated (JetBrains, Azure Storage Explorer, Docker, kubectl, ...) are listed with instructions.
* `NS_BUNDLE_DIR` overrides where the bundle is installed (useful for testing).
* Use a token limited to read access on the certificate endpoint, and rotate it if it was ever exposed (chat, ticket, script).

## Status
Developed and tested on Linux, including the Yarn (Classic and Berry), Mercurial and Conda paths
using stub executables. The API download was tested only against a local mock server (success, header fallback,
401/403, HTTP 500, bad JSON, empty list, no PEM, untrusted TLS). It has **not** been run against a real tenant. The Windows and macOS code paths follow the documented behaviour but
have not yet been run on those systems. Test before wide deployment.
