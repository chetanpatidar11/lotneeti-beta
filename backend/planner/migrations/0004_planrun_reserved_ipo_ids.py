from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("planner", "0003_alter_planrun_status")]

    operations = [
        migrations.AddField(
            model_name="planrun",
            name="reserved_ipo_ids",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
