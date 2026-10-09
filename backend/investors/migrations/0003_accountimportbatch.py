import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0005_workspace_auto_select_gmp_percent"),
        ("investors", "0002_demataccount"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountImportBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_filename", models.CharField(max_length=255)),
                ("source_hash", models.CharField(max_length=64)),
                ("rows_ciphertext", models.TextField()),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("error_count", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("PREVIEWED", "Previewed"), ("CONFIRMED", "Confirmed")], default="PREVIEWED", max_length=10)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="account_imports", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_imports", to="accounts.workspace")),
            ],
        ),
    ]
