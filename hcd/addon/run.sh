#!/usr/bin/with-contenv sh
# hcd add-on start: the options (/data/options.json) name the settings file and the log level.
# with-contenv: s6 passes the container's environment (SUPERVISOR_TOKEN, ...) only this way (0.1.1).
set -e
export PYTHONPATH=/opt/hcd PYTHONUNBUFFERED=1
cd /opt/hcd
CONFIG=$(/opt/venv/bin/python3 -c 'import json;print(json.load(open("/data/options.json")).get("config_file","/share/hcd/hcd.yaml"))')
LEVEL=$(/opt/venv/bin/python3 -c 'import json;print(json.load(open("/data/options.json")).get("log_level","info"))')
# 0.1.3: who else may open the page besides the ingress proxy (addresses or add-on host names, the add-on's options)
ALLOW=$(/opt/venv/bin/python3 -c 'import json;print(",".join(["172.30.32.2"]+[str(a) for a in json.load(open("/data/options.json")).get("web_allow") or []]))')
if [ ! -f "$CONFIG" ]; then
  echo "hcd: no settings file at $CONFIG – make one with hcd.import_ha (see the README)" >&2
  exit 1
fi
if [ -z "$SUPERVISOR_TOKEN" ]; then
  echo "hcd: SUPERVISOR_TOKEN is missing – Home Assistant and MQTT cannot be reached" >&2
fi
# 0.1.3 (security review): the page only for the ingress proxy; the service itself as the unprivileged "hcd" user,
# owning its own state in /data (options.json stays the Supervisor's)
# The settings file may hold a token and is the root's own (0600): a private copy in /data for the "hcd" user.
chown hcd:hcd /data
for f in /data/state.json /data/compare.sqlite /data/compare.sqlite-journal; do [ -e "$f" ] && chown hcd:hcd "$f"; done
install -m 600 -o hcd -g hcd "$CONFIG" /data/hcd.yaml
exec su-exec hcd /opt/venv/bin/python3 -m hcd --config /data/hcd.yaml --log-level "$LEVEL" \
  --web-host 0.0.0.0 --web-allow "$ALLOW"
