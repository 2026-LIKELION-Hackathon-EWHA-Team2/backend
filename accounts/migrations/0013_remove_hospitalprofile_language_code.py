from django.db import migrations


class Migration(migrations.Migration):
    # User.preferred_language is authoritative: it already controls translation.
    # Do not overwrite it with the profile field, whose independent default was en.
    # Removing the legacy column discards differing legacy values; back up before
    # deploying if those values need to be retained for auditing.
    dependencies = [
        ("accounts", "0012_alter_hospitalprofile_country_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="hospitalprofile",
            name="language_code",
        ),
    ]
