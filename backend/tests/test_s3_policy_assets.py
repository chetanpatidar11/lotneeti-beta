import json
from pathlib import Path


def test_beta_bucket_template_is_private_encrypted_and_scoped():
    root = Path(__file__).resolve().parents[2]
    template = json.loads((root / "deploy/aws/private-buckets.template.json").read_text())
    resources = template["Resources"]
    for name in ("ExportBucket", "BackupBucket"):
        settings = resources[name]["Properties"]
        assert settings["Tags"] == [
            {"Key": "Project", "Value": "LotNeeti"},
            {"Key": "Environment", "Value": "Beta"},
        ]
        assert all(settings["PublicAccessBlockConfiguration"].values())
        assert (
            settings["BucketEncryption"]["ServerSideEncryptionConfiguration"][0][
                "ServerSideEncryptionByDefault"
            ]["SSEAlgorithm"]
            == "AES256"
        )
        assert settings["OwnershipControls"]["Rules"][0]["ObjectOwnership"] == "BucketOwnerEnforced"
    for name in ("ExportBucketPolicy", "BackupBucketPolicy"):
        statements = resources[name]["Properties"]["PolicyDocument"]["Statement"]
        assert {item["Sid"] for item in statements} == {
            "DenyInsecureTransport",
            "DenyUnencryptedUploads",
        }
        assert all(item["Effect"] == "Deny" for item in statements)
    export_actions = resources["ExportAccessPolicy"]["Properties"]["PolicyDocument"]["Statement"]
    backup_actions = resources["BackupAccessPolicy"]["Properties"]["PolicyDocument"]["Statement"]
    assert export_actions[0]["Resource"]["Fn::Sub"].endswith("/exports/*")
    assert backup_actions[0]["Resource"]["Fn::Sub"].endswith("/backups/postgres/*")
    assert "s3:DeleteObject" not in export_actions[0]["Action"]
    role = resources["BetaInstanceRole"]["Properties"]
    assert role["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {
        "Service": "ec2.amazonaws.com"
    }
    assert role["ManagedPolicyArns"] == [
        {"Ref": "ExportAccessPolicy"},
        {"Ref": "BackupAccessPolicy"},
        {"Fn::If": ["HasSESSender", {"Ref": "SESAccessPolicy"}, {"Ref": "AWS::NoValue"}]},
    ]
    ses_policy = resources["SESAccessPolicy"]
    assert ses_policy["Condition"] == "HasSESSender"
    assert ses_policy["Properties"]["PolicyDocument"]["Statement"] == [
        {
            "Effect": "Allow",
            "Action": "ses:SendRawEmail",
            "Resource": {
                "Fn::Sub": (
                    "arn:${AWS::Partition}:ses:${AWS::Region}:${AWS::AccountId}:"
                    "identity/${SESSenderEmail}"
                )
            },
        }
    ]
    assert resources["BetaInstanceProfile"]["Properties"]["Roles"] == [{"Ref": "BetaInstanceRole"}]
