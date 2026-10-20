from django.db import migrations


def seed_restrictions(apps, schema_editor):
    restriction = apps.get_model("funding", "BankFundingRestriction")
    for name, aliases in (
        ("IDFC", "IDFC FIRST BANK\nIDFC FIRST\nIDFC BANK\nIDFC FIRST BANK LTD\nIDFC FIRST BANK LIMITED"),
        ("BOI", "BANK OF INDIA"),
    ):
        restriction.objects.get_or_create(
            name=name,
            defaults={
                "aliases": aliases,
                "active": True,
                "reason": "Founder cross-funding preference",
            },
        )


class Migration(migrations.Migration):
    dependencies = [("funding", "0014_bank_funding_restriction")]

    operations = [migrations.RunPython(seed_restrictions, migrations.RunPython.noop)]
