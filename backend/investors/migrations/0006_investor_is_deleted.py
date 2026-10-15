from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("investors", "0005_demataccount_one_demat_per_investor"),
    ]

    operations = [
        migrations.AddField(
            model_name="investor",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
