#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: bash deploy/push-from-workstation.sh PUBLIC_IP SSH_PRIVATE_KEY BETA_HOSTNAME" >&2
  exit 2
fi
public_ip=$1
ssh_key=$2
beta_hostname=$3
if [[ ! "$public_ip" =~ ^[0-9.]+$ ]] || [[ ! "$beta_hostname" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "Invalid IP address or hostname" >&2
  exit 2
fi
if [[ ! -f "$ssh_key" ]]; then
  echo "SSH private key not found" >&2
  exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
archive=$(mktemp /private/tmp/lotneeti-release.XXXXXX)
remote_archive="/tmp/lotneeti-release-$(date -u +%Y%m%dT%H%M%SZ)-$$.tar.gz"
trap 'rm -f "$archive"' EXIT
ssh_options=(-i "$ssh_key" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "${LOTNEETI_KNOWN_HOSTS:-}" ]]; then
  ssh_options+=(-o "UserKnownHostsFile=$LOTNEETI_KNOWN_HOSTS")
fi

cd "$repo_root"
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$archive" \
  --exclude='node_modules' --exclude='.next' --exclude='__pycache__' \
  --exclude='.pytest_cache' --exclude='staticfiles' --exclude='.ruff_cache' \
  backend web deploy
shasum -a 256 "$archive"
scp "${ssh_options[@]}" "$archive" "ubuntu@$public_ip:$remote_archive"
ssh "${ssh_options[@]}" "ubuntu@$public_ip" \
  "sudo bash -s -- '$remote_archive' '$beta_hostname'" <<'REMOTE'
set -euo pipefail
remote_archive=$1
beta_hostname=$2
release_dir=$(mktemp -d /tmp/lotneeti-unpack.XXXXXX)
trap 'rm -rf "$release_dir" "$remote_archive"' EXIT
chown lotneeti:lotneeti "$release_dir"
chown lotneeti:lotneeti "$remote_archive"
runuser -u lotneeti -- tar -xzf "$remote_archive" -C "$release_dir"
for part in backend web deploy; do
  runuser -u lotneeti -- rsync -a --delete \
    --exclude='node_modules/' --exclude='.next/' --exclude='staticfiles/' \
    --exclude='__pycache__/' --exclude='.pytest_cache/' --exclude='.ruff_cache/' \
    "$release_dir/$part/" "/opt/lotneeti/$part/"
done
cp /opt/lotneeti/deploy/systemd/lotneeti-*.service /etc/systemd/system/
cp /opt/lotneeti/deploy/systemd/lotneeti-backup.timer /etc/systemd/system/
install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
install -m 755 /opt/lotneeti/deploy/letsencrypt/reload-nginx.sh \
  /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
sed "s/__DOMAIN__/$beta_hostname/g" \
  /opt/lotneeti/deploy/nginx/lotneeti.conf.template \
  >/etc/nginx/sites-available/lotneeti.conf
nginx -t
systemctl daemon-reload
systemctl reload nginx
bash /opt/lotneeti/deploy/deploy.sh
REMOTE

curl --fail --silent --show-error "https://$beta_hostname/api/v1/health/"
printf '\nDeployment complete: https://%s/\n' "$beta_hostname"
