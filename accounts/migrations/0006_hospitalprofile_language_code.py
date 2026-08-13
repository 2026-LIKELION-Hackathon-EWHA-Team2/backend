from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_merge_20260810_1526"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospitalprofile",
            name="language_code",
            field=models.CharField(default="en", max_length=10),
        ),
    ]
