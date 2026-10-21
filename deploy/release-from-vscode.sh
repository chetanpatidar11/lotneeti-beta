#!/usr/bin/env bash
set -euo pipefail

# Run from the workstation terminal that has the current AWS login.
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
region=us-east-1
instance_id=i-02def39354f6c2377
availability_zone=us-east-1a
public_ip=54.208.70.218
hostname=lotneeti.dpdns.org
known_hosts=${LOTNEETI_KNOWN_HOSTS:-"$HOME/Documents/Codex/lotneeti-eip-known-hosts"}

if [[ ! -f "$known_hosts" ]]; then
  echo "Pinned SSH host key file missing: $known_hosts" >&2
  exit 1
fi
account=$(aws sts get-caller-identity --query Account --output text)
if [[ "$account" != 497502378741 ]]; then
  echo "AWS is signed in to a different account; deployment stopped." >&2
  exit 1
fi
current_ip=$(aws ec2 describe-instances --region "$region" --instance-ids "$instance_id" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
if [[ "$current_ip" != "$public_ip" ]]; then
  echo "The server IP has changed; deployment stopped." >&2
  exit 1
fi

python3 "$repo_root/deploy/ssh_access.py"

temporary_keys=$(mktemp -d /private/tmp/lotneeti-release-keys.XXXXXX)
trap 'rm -rf "$temporary_keys"' EXIT
ssh-keygen -q -t ed25519 -N '' -f "$temporary_keys/id_ed25519"

authorize_key() {
  local granted
  granted=$(aws ec2-instance-connect send-ssh-public-key --region "$region" \
    --instance-id "$instance_id" --availability-zone "$availability_zone" \
    --instance-os-user ubuntu \
    --ssh-public-key "file://$temporary_keys/id_ed25519.pub" \
    --query Success --output text)
  if [[ "$granted" != True ]]; then
    echo "Temporary SSH access was not granted; deployment stopped." >&2
    exit 1
  fi
}

authorize_key
backup_result=$(ssh -i "$temporary_keys/id_ed25519" -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known_hosts" \
  "ubuntu@$public_ip" \
  'sudo systemctl start lotneeti-backup.service && sudo systemctl show lotneeti-backup.service -p Result -p ExecMainStatus')
if [[ "$backup_result" != *"Result=success"* || "$backup_result" != *"ExecMainStatus=0"* ]]; then
  echo "The pre-release backup did not succeed; deployment stopped." >&2
  exit 1
fi
echo "Pre-release backup succeeded."

authorize_key
LOTNEETI_KNOWN_HOSTS="$known_hosts" bash "$repo_root/deploy/push-from-workstation.sh" \
  "$public_ip" "$temporary_keys/id_ed25519" "$hostname"
