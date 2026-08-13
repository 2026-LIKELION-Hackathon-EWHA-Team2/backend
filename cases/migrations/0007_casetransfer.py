import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cases", "0006_caseagreement_caseagreementrevision_and_more"),
        ("selfsymptoms", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseTransfer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("patient_name", models.CharField(max_length=100)),
                (
                    "patient_gender",
                    models.CharField(
                        choices=[
                            ("FEMALE", "여성"),
                            ("MALE", "남성"),
                            ("OTHER", "기타"),
                        ],
                        max_length=20,
                    ),
                ),
                ("patient_birth_date", models.DateField()),
                ("target_language", models.CharField(max_length=10)),
                ("translated_data", models.JSONField(default=dict)),
                ("structured_data", models.JSONField(default=dict)),
                (
                    "processing_error",
                    models.TextField(blank=True, default=""),
                ),
                ("adverse_effects", models.JSONField(default=list)),
                ("include_patient_info", models.BooleanField(default=False)),
                ("include_procedure_info", models.BooleanField(default=False)),
                ("include_adverse_effects", models.BooleanField(default=False)),
                ("include_clinician_note", models.BooleanField(default=False)),
                ("privacy_agreed", models.BooleanField(default=False)),
                ("medical_info_agreed", models.BooleanField(default=False)),
                ("overseas_transfer_agreed", models.BooleanField(default=False)),
                ("agreed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PROCESSING", "번역·구조화 중"),
                            ("REVIEW_REQUIRED", "최종 확인 필요"),
                            ("PROCESSING_FAILED", "번역·구조화 실패"),
                            ("READY_TO_TRANSFER", "전송 준비 완료"),
                            ("TRANSFERRED", "전송 완료"),
                        ],
                        default="PROCESSING",
                        max_length=30,
                    ),
                ),
                ("transferred_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "medical_case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="case_transfers",
                        to="cases.medicalcase",
                    ),
                ),
                (
                    "partner_hospital",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="received_case_transfers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="case_transfers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "symptom_case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="case_transfers",
                        to="selfsymptoms.patientsymptomcase",
                    ),
                ),
            ],
        ),
    ]
