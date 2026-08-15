import unicodedata

from django.db import migrations, models


SPECIALTY_NAMES_BY_CODE = {
    "ACNE_SCAR": "여드름·흉터",
    "PIGMENTATION": "색소",
    "LIFTING": "리프팅",
    "BOTOX_FILLER": "보톡스·필러",
    "BREAST_BODY": "가슴·바디",
    "EYE": "눈",
    "NOSE": "코",
    "CONTOURING": "윤곽",
    "HAIR_REMOVAL": "제모",
}


def normalize_name(value):
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.translate(
        str.maketrans({".": "·", "ㆍ": "·", "・": "·"})
    )
    return " ".join(normalized.split()).casefold()


def populate_specialty_codes(apps, schema_editor):
    medical_specialty = apps.get_model(
        "accounts",
        "MedicalSpecialty",
    )
    codes_by_name = {
        normalize_name(name): code
        for code, name in SPECIALTY_NAMES_BY_CODE.items()
    }

    for specialty in medical_specialty.objects.all().iterator():
        specialty.specialty_code = codes_by_name.get(
            normalize_name(specialty.specialty_name),
            "CUSTOM",
        )
        specialty.save(update_fields=["specialty_code"])


class Migration(migrations.Migration):
    dependencies = [
        (
            "accounts",
            "0007_patientprofile_address_user_location_info_agreed_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="medicalspecialty",
            name="specialty_code",
            field=models.CharField(
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
                default="CUSTOM",
                max_length=30,
            ),
        ),
        migrations.RunPython(
            populate_specialty_codes,
            migrations.RunPython.noop,
        ),
    ]
