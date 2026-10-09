import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_workspace_auto_select_gmp_percent"),
        ("core", "0002_betaevent"),
    ]

    operations = [
        migrations.CreateModel(
            name="FeatureFlag",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=100)),
                ("enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_flags",
                        to="accounts.workspace",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="featureflag",
            constraint=models.UniqueConstraint(
                condition=Q(workspace__isnull=True),
                fields=("key",),
                name="unique_platform_feature_flag",
            ),
        ),
        migrations.AddConstraint(
            model_name="featureflag",
            constraint=models.UniqueConstraint(
                condition=Q(workspace__isnull=False),
                fields=("key", "workspace"),
                name="unique_workspace_feature_flag",
            ),
        ),
    ]
