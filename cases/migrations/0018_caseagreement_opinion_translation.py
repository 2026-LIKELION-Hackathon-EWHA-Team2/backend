from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0017_caseagreement_localized_content"),
    ]

    operations = [
        migrations.AddField(
            model_name="caseagreement",
            name="additional_opinion_source_language",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="caseagreement",
            name="additional_opinion_translation_error_code",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="caseagreement",
            name="additional_opinion_translation_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "번역 없음"),
                    ("PENDING", "번역 중"),
                    ("COMPLETED", "번역 완료"),
                    ("FAILED", "번역 실패"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="caseagreement",
            name="additional_opinion_translations",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
