from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "accounts",
            "0008_medicalspecialty_specialty_code",
        ),
        ("matching", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospitalmatchrequest",
            name="required_specialty_code",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ACNE_SCAR", "여드름·흉터"),
                    ("PIGMENTATION", "색소"),
                    ("LIFTING", "리프팅"),
                    ("BOTOX_FILLER", "보톡스·필러"),
                    ("BREAST_BODY", "가슴·바디"),
                    ("EYE", "눈"),
                    ("NOSE", "코"),
                    ("CONTOURING", "윤곽"),
                    ("HAIR_REMOVAL", "제모"),
                    ("CUSTOM", "직접 추가하기"),
                ],
                max_length=30,
                null=True,
            ),
        ),
    ]
