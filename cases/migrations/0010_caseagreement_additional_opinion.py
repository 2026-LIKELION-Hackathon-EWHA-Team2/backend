from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0009_rename_casetransfer_agreement_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="caseagreement",
            name="additional_opinion",
            field=models.TextField(blank=True, default=""),
        ),
    ]
