import json
from pathlib import Path


def test_ec2_beta_template_is_single_host_and_restricts_network_and_metadata():
    root = Path(__file__).resolve().parents[2]
    template = json.loads((root / "deploy/aws/ec2-beta.template.json").read_text())
    resources = template["Resources"]
    assert [name for name, item in resources.items() if item["Type"] == "AWS::EC2::Instance"] == [
        "BetaInstance"
    ]
    assert not any(
        item["Type"] in {"AWS::EC2::NatGateway", "AWS::ElasticLoadBalancingV2::LoadBalancer"}
        for item in resources.values()
    )
    instance = resources["BetaInstance"]["Properties"]
    assert instance["MetadataOptions"]["HttpTokens"] == "required"
    assert instance["CreditSpecification"]["CPUCredits"] == "standard"
    assert instance["BlockDeviceMappings"][0]["Ebs"]["Encrypted"] is True
    assert instance["IamInstanceProfile"] == {"Ref": "InstanceProfileName"}
    ingress = resources["BetaSecurityGroup"]["Properties"]["SecurityGroupIngress"]
    assert [(rule["FromPort"], rule["CidrIp"]) for rule in ingress[1:]] == [
        (80, "0.0.0.0/0"),
        (443, "0.0.0.0/0"),
    ]
    assert ingress[0]["CidrIp"] == {"Ref": "OperatorCidr"}
