from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_user_location_info_agreed"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="overseas_transfer_agreed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="address",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
