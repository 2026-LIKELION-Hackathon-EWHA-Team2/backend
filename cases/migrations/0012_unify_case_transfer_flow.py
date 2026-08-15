import django.db.models.deletion
from django.db import migrations, models


def move_legacy_cases_to_ready(apps, schema_editor):
    medical_case = apps.get_model("cases", "MedicalCase")
    medical_case.objects.filter(
        status="WAITING_PATIENT",
    ).update(status="READY_TO_TRANSFER")


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0011_remove_caseagreement_follow_up_fields"),
        ("matching", "0002_hospitalmatchrequest_required_specialty_code"),
    ]

    operations = [
        migrations.RunPython(
            move_legacy_cases_to_ready,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="medicalcase",
            name="status",
            field=models.CharField(
                choices=[
                    ("READY_TO_TRANSFER", "전송 동의 대기"),
                    ("TRANSFERRED", "전송 완료"),
                ],
                default="READY_TO_TRANSFER",
                max_length=30,
            ),
        ),
        migrations.DeleteModel(
            name="CaseSyncRequest",
        ),
        migrations.RemoveField(
            model_name="medicalcase",
            name="procedure_info_agreed",
        ),
        migrations.RemoveField(
            model_name="medicalcase",
            name="adverse_effect_info_agreed",
        ),
        migrations.RemoveField(
            model_name="medicalcase",
            name="overseas_transfer_agreed",
        ),
        migrations.AddField(
            model_name="casetransfer",
            name="recommendation",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="case_transfer",
                to="matching.hospitalrecommendation",
            ),
        ),
        migrations.AddConstraint(
            model_name="casetransfer",
            constraint=models.UniqueConstraint(
                fields=("symptom_case",),
                name="unique_symptom_case_transfer",
            ),
        ),
    ]
