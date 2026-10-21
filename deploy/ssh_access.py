#!/usr/bin/env python3
"""Keep the existing operator SSH rule restricted to this workstation's IPv4."""

import ipaddress
import json
import socket
import subprocess
import sys
import time


REGION = "us-east-1"
ACCOUNT_ID = "497502378741"
INSTANCE_ID = "i-02def39354f6c2377"
PUBLIC_IP = "54.208.70.218"
GROUP_ID = "sg-0def099f971811fba"


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def aws(*args):
    return json.loads(command("aws", *args, "--region", REGION, "--output", "json"))


def select_ssh_rule(rules):
    matches = [
        rule
        for rule in rules
        if not rule.get("IsEgress")
        and rule.get("IpProtocol") == "tcp"
        and rule.get("FromPort") == 22
        and rule.get("ToPort") == 22
        and rule.get("CidrIpv4")
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one IPv4 SSH rule in {GROUP_ID}; found {len(matches)}. "
            "No security group changes were made."
        )
    return matches[0]


def modification(rule, cidr):
    setting = {
        "IpProtocol": "tcp",
        "FromPort": 22,
        "ToPort": 22,
        "CidrIpv4": cidr,
    }
    if rule.get("Description"):
        setting["Description"] = rule["Description"]
    return {
        "GroupId": GROUP_ID,
        "SecurityGroupRules": [
            {"SecurityGroupRuleId": rule["SecurityGroupRuleId"], "SecurityGroupRule": setting}
        ],
    }


def main():
    account = aws("sts", "get-caller-identity").get("Account")
    if account != ACCOUNT_ID:
        raise ValueError("AWS CLI is signed in to a different account; stopped.")

    reservations = aws("ec2", "describe-instances", "--instance-ids", INSTANCE_ID)["Reservations"]
    instances = [instance for reservation in reservations for instance in reservation["Instances"]]
    if len(instances) != 1 or instances[0].get("PublicIpAddress") != PUBLIC_IP:
        raise ValueError("The expected production instance or public IP was not found; stopped.")
    if GROUP_ID not in {group["GroupId"] for group in instances[0]["SecurityGroups"]}:
        raise ValueError("The expected security group is not attached to production; stopped.")

    ip = ipaddress.IPv4Address(command("curl", "-4fsS", "--max-time", "10", "https://checkip.amazonaws.com"))
    cidr = f"{ip}/32"
    rules = aws(
        "ec2", "describe-security-group-rules", "--filters", f"Name=group-id,Values={GROUP_ID}"
    )["SecurityGroupRules"]
    rule = select_ssh_rule(rules)
    previous_cidr = rule["CidrIpv4"]
    if previous_cidr != cidr:
        result = aws(
            "ec2", "modify-security-group-rules", "--cli-input-json", json.dumps(modification(rule, cidr))
        )
        if result.get("Return") is not True:
            raise ValueError("AWS did not confirm the SSH rule update; stopped.")
        print(f"SSH access updated from {previous_cidr} to {cidr}.")
    else:
        print(f"SSH access already limited to {cidr}.")

    for _ in range(5):
        try:
            with socket.create_connection((PUBLIC_IP, 22), timeout=3):
                print("SSH port is reachable; continuing release.")
                return
        except OSError:
            time.sleep(2)
    raise ValueError(
        "SSH port 22 remains unreachable. Check VPN or the instance network rules; release stopped."
    )


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, subprocess.CalledProcessError) as error:
        print(f"SSH access check failed: {error}", file=sys.stderr)
        sys.exit(1)
