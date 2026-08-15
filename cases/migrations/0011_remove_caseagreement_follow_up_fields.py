from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0010_caseagreement_additional_opinion"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="caseagreement",
            name="observation_days",
        ),
        migrations.RemoveField(
            model_name="caseagreement",
            name="photo_upload_date",
        ),
        migrations.RemoveField(
            model_name="caseagreement",
            name="follow_up_date",
        ),
        migrations.RemoveField(
            model_name="caseagreement",
            name="precautions",
        ),
        migrations.RemoveField(
            model_name="caseagreement",
            name="patient_message",
        ),
    ]
