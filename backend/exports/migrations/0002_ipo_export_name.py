from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("exports", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="planexport",
            name="download_filename",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="planexport",
            name="ipo_ref",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
