#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the beta EC2 host" >&2
  exit 1
fi
if [[ "$(. /etc/os-release && printf '%s:%s' "$ID" "$VERSION_ID")" != "ubuntu:24.04" ]]; then
  echo "This bootstrap requires Ubuntu 24.04" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg postgresql-common

install -d -m 755 /usr/share/postgresql-common/pgdg
curl --fail --silent --show-error \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
cat >/etc/apt/sources.list.d/pgdg.sources <<'EOF'
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: noble-pgdg
Architectures: arm64
Components: main
Signed-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
EOF

curl --fail --silent --show-error \
  https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg
cat >/etc/apt/sources.list.d/nodesource.sources <<'EOF'
Types: deb
URIs: https://deb.nodesource.com/node_22.x
Suites: nodistro
Architectures: arm64
Components: main
Signed-By: /usr/share/keyrings/nodesource.gpg
EOF

apt-get update
apt-get install -y \
  build-essential certbot git libpq-dev nginx nodejs postgresql-17 \
  postgresql-client-17 python3-dev python3-pip python3-venv redis-server rsync

if [[ ! -e /swapfile ]]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >>/etc/fstab
  swapon /swapfile
fi

timedatectl set-timezone Asia/Kolkata
if ! id lotneeti >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin lotneeti
fi
install -d -m 755 -o lotneeti -g lotneeti /opt/lotneeti /var/lib/lotneeti
install -d -m 700 -o root -g root /etc/lotneeti
install -d -m 755 /var/www/letsencrypt
systemctl enable --now postgresql redis-server nginx

python3 --version
node --version
psql --version
redis-server --version
