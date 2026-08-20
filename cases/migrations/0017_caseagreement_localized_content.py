from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0016_alter_casetransfer_patient_birth_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="caseagreement",
            name="localized_content",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
