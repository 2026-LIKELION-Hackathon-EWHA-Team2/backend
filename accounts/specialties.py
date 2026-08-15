import unicodedata

from django.db import models


class SpecialtyCode(models.TextChoices):
    ACNE_SCAR = "ACNE_SCAR", "여드름·흉터"
    PIGMENTATION = "PIGMENTATION", "색소"
    LIFTING = "LIFTING", "리프팅"
    BOTOX_FILLER = "BOTOX_FILLER", "보톡스·필러"
    BREAST_BODY = "BREAST_BODY", "가슴·바디"
    EYE = "EYE", "눈"
    NOSE = "NOSE", "코"
    CONTOURING = "CONTOURING", "윤곽"
    HAIR_REMOVAL = "HAIR_REMOVAL", "제모"
    CUSTOM = "CUSTOM", "직접 추가하기"


MAX_SPECIALTY_SELECTIONS = 20


def normalize_specialty_name(value):
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.translate(
        str.maketrans(
            {
                ".": "·",
                "ㆍ": "·",
                "・": "·",
            }
        )
    )
    return " ".join(normalized.split()).casefold()


def get_specialty_code_for_name(name):
    normalized_name = normalize_specialty_name(name)

    for code, label in SpecialtyCode.choices:
        if code == SpecialtyCode.CUSTOM:
            continue

        if normalize_specialty_name(label) == normalized_name:
            return code

    return SpecialtyCode.CUSTOM


def get_specialty_name(code, custom_name=""):
    if code == SpecialtyCode.CUSTOM:
        return " ".join(custom_name.split())

    return SpecialtyCode(code).label
