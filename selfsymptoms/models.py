from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import PatientProfile


class PatientSymptomCase(models.Model):
    class OnsetTiming(models.TextChoices):
        IMMEDIATE = "IMMEDIATE", "즉시"
        AFTER_1_DAY = "AFTER_1_DAY", "1일 후"
        AFTER_2_3_DAYS = "AFTER_2_3_DAYS", "2~3일 후"
        AFTER_4_7_DAYS = "AFTER_4_7_DAYS", "4~7일 후"
        AFTER_1_WEEK = "AFTER_1_WEEK", "1주 이후"
        UNKNOWN = "UNKNOWN", "정확히 모름"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "작성 중"
        SUBMITTED = "SUBMITTED", "작성 완료"
        MATCHING = "MATCHING", "병원 매칭 중"
        HOSPITAL_SELECTED = "HOSPITAL_SELECTED", "병원 선택 완료"
        CONNECTION_REQUESTED = "CONNECTION_REQUESTED", "연결 요청 완료"
        COMPLETED = "COMPLETED", "완료"
        CANCELLED = "CANCELLED", "취소"

    symptom_case_id = models.BigAutoField(
        primary_key=True,
    )

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="symptom_cases",
    )

    symptom_start_date = models.DateField(
        null=True,
        blank=True,
    )

    onset_timing = models.CharField(
        max_length=30,
        choices=OnsetTiming.choices,
        null=True,
        blank=True,
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    pain_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "PATIENT_SYMPTOM_CASE"
        ordering = ["-created_at"]

    def clean(self):
        if self.pain_level is not None:
            if self.pain_level < 1 or self.pain_level > 5:
                raise ValidationError(
                    {
                        "pain_level": "통증 정도는 1부터 5 사이여야 합니다."
                    }
                )

    def __str__(self):
        return (
            f"증상 기록 {self.symptom_case_id} "
            f"- 환자 {self.patient.patient_id}"
        )


class PatientSymptomImage(models.Model):
    symptom_image_id = models.BigAutoField(
        primary_key=True,
    )

    symptom_case = models.ForeignKey(
        PatientSymptomCase,
        on_delete=models.CASCADE,
        related_name="images",
    )

    image = models.ImageField(
        upload_to="symptom_images/%Y/%m/%d/",
    )

    display_order = models.PositiveSmallIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "PATIENT_SYMPTOM_IMAGE"
        ordering = ["display_order", "created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "symptom_case",
                    "display_order",
                ],
                name="unique_symptom_image_order",
            )
        ]

    def clean(self):
        if self.display_order < 1 or self.display_order > 6:
            raise ValidationError(
                {
                    "display_order": "사진 순서는 1부터 6 사이여야 합니다."
                }
            )

        if self.symptom_case_id:
            image_count = (
                PatientSymptomImage.objects
                .filter(symptom_case_id=self.symptom_case_id)
                .exclude(pk=self.pk)
                .count()
            )

            if image_count >= 6:
                raise ValidationError(
                    "사진은 최대 6장까지 등록할 수 있습니다."
                )

    def __str__(self):
        return f"증상 사진 {self.symptom_image_id}"


class PatientSymptomArea(models.Model):
    class AreaType(models.TextChoices):
        FACE = "FACE", "얼굴 전체"
        FOREHEAD = "FOREHEAD", "이마"
        EYE = "EYE", "눈"
        NOSE = "NOSE", "코"
        CHEEK = "CHEEK", "볼"
        MOUTH = "MOUTH", "입술 및 입 주변"
        CHIN = "CHIN", "턱"
        NECK = "NECK", "목"
        CHEST = "CHEST", "가슴"
        ABDOMEN = "ABDOMEN", "복부"
        ARM = "ARM", "팔"
        HAND = "HAND", "손"
        LEG = "LEG", "다리"
        FOOT = "FOOT", "발"
        OTHER = "OTHER", "기타"

    symptom_area_id = models.BigAutoField(
        primary_key=True,
    )

    symptom_case = models.ForeignKey(
        PatientSymptomCase,
        on_delete=models.CASCADE,
        related_name="areas",
    )

    area_type = models.CharField(
        max_length=30,
        choices=AreaType.choices,
    )

    custom_area = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "PATIENT_SYMPTOM_AREA"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "symptom_case",
                    "area_type",
                ],
                name="unique_symptom_area",
            )
        ]

    def clean(self):
        if self.area_type == self.AreaType.OTHER:
            if not self.custom_area:
                raise ValidationError(
                    {
                        "custom_area": (
                            "기타 부위를 선택한 경우 "
                            "부위를 직접 입력해야 합니다."
                        )
                    }
                )
        else:
            if self.custom_area:
                raise ValidationError(
                    {
                        "custom_area": (
                            "기타 부위를 선택한 경우에만 "
                            "직접 입력할 수 있습니다."
                        )
                    }
                )

    def __str__(self):
        if self.area_type == self.AreaType.OTHER:
            return self.custom_area

        return self.get_area_type_display()


class PatientSymptomType(models.Model):
    class SymptomType(models.TextChoices):
        REDNESS = "REDNESS", "붉음"
        SWELLING = "SWELLING", "붓기"
        PAIN = "PAIN", "통증"
        BRUISING = "BRUISING", "멍"
        BLEEDING = "BLEEDING", "출혈"
        DISCHARGE = "DISCHARGE", "분비물"
        ITCHING = "ITCHING", "가려움"
        HEAT = "HEAT", "열감"
        NUMBNESS = "NUMBNESS", "감각 저하"
        ASYMMETRY = "ASYMMETRY", "비대칭"
        WOUND_OPENING = "WOUND_OPENING", "상처 벌어짐"
        OTHER = "OTHER", "기타"

    symptom_type_id = models.BigAutoField(
        primary_key=True,
    )

    symptom_case = models.ForeignKey(
        PatientSymptomCase,
        on_delete=models.CASCADE,
        related_name="symptom_types",
    )

    symptom_type = models.CharField(
        max_length=30,
        choices=SymptomType.choices,
    )

    custom_symptom = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "PATIENT_SYMPTOM_TYPE"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "symptom_case",
                    "symptom_type",
                ],
                name="unique_symptom_type",
            )
        ]

    def clean(self):
        if self.symptom_type == self.SymptomType.OTHER:
            if not self.custom_symptom:
                raise ValidationError(
                    {
                        "custom_symptom": (
                            "기타 증상을 선택한 경우 "
                            "증상을 직접 입력해야 합니다."
                        )
                    }
                )
        else:
            if self.custom_symptom:
                raise ValidationError(
                    {
                        "custom_symptom": (
                            "기타 증상을 선택한 경우에만 "
                            "직접 입력할 수 있습니다."
                        )
                    }
                )

    def __str__(self):
        if self.symptom_type == self.SymptomType.OTHER:
            return self.custom_symptom

        return self.get_symptom_type_display()
# Create your models here.
