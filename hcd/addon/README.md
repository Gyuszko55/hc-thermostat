# HC daemon (hcd) – local add-on

HC Thermostat's decision core running outside Home Assistant's core. Phase F2: **shadow mode** – every minute it
decides as the HC integration would, compares, and switches nothing. Its page is in the sidebar (ingress).

- Settings: `/share/hcd/hcd.yaml` (made by `hcd.import_ha` from an HC instance's diagnostics, then each source bound
  to its feed: `ha`, `z2m`, `shelly_rpc`; `mqtt: {host: supervisor}` takes the broker from the Supervisor).
- State and comparison: the add-on's `/data` (`state.json`, `compare.sqlite`); `seed_state` starts from the
  integration's state.
- Security (0.1.3): the page answers only the Supervisor's ingress proxy (no port is published, other add-ons get
  `403`); the service runs as the unprivileged `hcd` user with a private copy of the settings in `/data`
  (`/share` is mapped read-only); fixed package versions. `homeassistant_api` stays on – hcd reads states over the
  Core API, and the Supervisor has no read-only scope for that.
- `web_allow` (option): addresses or add-on host names (e.g. another add-on's `xxxxxxxx-name`) let in besides the
  ingress proxy – host names are resolved, so a restarted container still gets in.
- Run by hand (`python -m hcd --config …`) the page listens on `127.0.0.1` only; `web_host` / `web_allow` in the
  settings (or `--web-host` / `--web-allow`) open it deliberately.
- Installing: copy this folder to the `addons` Samba share as `hcd`, then Add-on store → ⋮ → Check for updates →
  Local add-ons → HC daemon (hcd).
