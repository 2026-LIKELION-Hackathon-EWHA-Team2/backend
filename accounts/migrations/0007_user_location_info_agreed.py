from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_hospitalprofile_language_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="location_info_agreed",
            field=models.BooleanField(default=False),
        ),
    ]
