#!/usr/bin/env bash
set -euo pipefail

app_root=/opt/lotneeti
app_env=/etc/lotneeti/app.env
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the prepared beta host" >&2
  exit 1
fi
if [[ ! -r "$app_env" ]]; then
  echo "Missing $app_env" >&2
  exit 1
fi
if [[ ! -f "$app_root/backend/manage.py" ]]; then
  echo "Missing LotNeeti checkout at $app_root" >&2
  exit 1
fi
cd "$app_root"

set -a
source "$app_env"
set +a
export DJANGO_SETTINGS_MODULE=config.settings.prod

runuser -u lotneeti -- python3 -m venv "$app_root/.venv"
runuser -u lotneeti -- "$app_root/.venv/bin/python" -m pip install --no-cache-dir -e "$app_root/backend"
runuser -u lotneeti -- npm ci --prefix "$app_root/web"
runuser -u lotneeti -- npm --prefix "$app_root/web" run build
runuser -u lotneeti -- "$app_root/.venv/bin/python" "$app_root/backend/manage.py" check --deploy
runuser -u lotneeti -- "$app_root/.venv/bin/python" "$app_root/backend/manage.py" migrate --noinput
runuser -u lotneeti -- "$app_root/.venv/bin/python" "$app_root/backend/manage.py" collectstatic --noinput

systemctl restart lotneeti-api.service lotneeti-worker.service lotneeti-beat.service lotneeti-web.service
systemctl is-active --quiet lotneeti-api.service
systemctl is-active --quiet lotneeti-worker.service
systemctl is-active --quiet lotneeti-beat.service
systemctl is-active --quiet lotneeti-web.service
