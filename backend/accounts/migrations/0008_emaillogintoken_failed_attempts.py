from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_workspace_auto_select_issue_types")]

    operations = [
        migrations.AddField(
            model_name="emaillogintoken",
            name="failed_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
