#!/bin/sh
# Puts the hcd add-on together in one folder (default /share/hcd-addon/hcd): the add-on files, the core as hc_core
# and the hcd package – copy that folder to the `addons` Samba share.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-/share/hcd-addon/hcd}
rm -rf "$OUT"
mkdir -p "$OUT"
cp "$ROOT"/hcd/addon/config.yaml "$ROOT"/hcd/addon/build.yaml "$ROOT"/hcd/addon/Dockerfile "$ROOT"/hcd/addon/run.sh \
   "$ROOT"/hcd/addon/README.md "$OUT"/
mkdir -p "$OUT"/hc_core "$OUT"/hcd
cp "$ROOT"/custom_components/hc_thermostat/core/*.py "$OUT"/hc_core/
cp "$ROOT"/hcd/hcd/*.py "$OUT"/hcd/
cp "$ROOT"/LICENSE "$OUT"/
echo "hcd add-on → $OUT ($(ls "$OUT"/hc_core | wc -l) core files)"
