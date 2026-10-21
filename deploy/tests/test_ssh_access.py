import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[1] / "ssh_access.py"
spec = importlib.util.spec_from_file_location("ssh_access", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SshAccessTests(unittest.TestCase):
    def test_selects_only_inbound_tcp_22_ipv4_rule(self):
        rule = {
            "SecurityGroupRuleId": "sgr-123",
            "IsEgress": False,
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "CidrIpv4": "203.0.113.4/32",
            "Description": "Operator access",
        }
        rules = [
            {**rule, "IsEgress": True},
            {**rule, "FromPort": 443, "ToPort": 443},
            {**rule, "CidrIpv4": None, "CidrIpv6": "::/0"},
            rule,
        ]
        self.assertEqual(module.select_ssh_rule(rules), rule)
        self.assertEqual(
            module.modification(rule, "198.51.100.5/32"),
            {
                "GroupId": module.GROUP_ID,
                "SecurityGroupRules": [
                    {
                        "SecurityGroupRuleId": "sgr-123",
                        "SecurityGroupRule": {
                            "IpProtocol": "tcp",
                            "FromPort": 22,
                            "ToPort": 22,
                            "CidrIpv4": "198.51.100.5/32",
                            "Description": "Operator access",
                        },
                    }
                ],
            },
        )

    def test_refuses_ambiguous_ssh_rules(self):
        rule = {
            "SecurityGroupRuleId": "sgr-123",
            "IsEgress": False,
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "CidrIpv4": "203.0.113.4/32",
        }
        with self.assertRaisesRegex(ValueError, "Expected one"):
            module.select_ssh_rule([])
        with self.assertRaisesRegex(ValueError, "Expected one"):
            module.select_ssh_rule([rule, {**rule, "SecurityGroupRuleId": "sgr-456"}])


if __name__ == "__main__":
    unittest.main()
