from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0008_alter_medicalcase_partner_hospital"),
    ]

    operations = [
        migrations.RenameField(
            model_name="casetransfer",
            old_name="privacy_agreed",
            new_name="procedure_medication_agreed",
        ),
        migrations.RenameField(
            model_name="casetransfer",
            old_name="medical_info_agreed",
            new_name="adverse_effect_clinician_note_agreed",
        ),
        migrations.RenameField(
            model_name="casetransfer",
            old_name="overseas_transfer_agreed",
            new_name="overseas_ai_processing_agreed",
        ),
    ]
