from django.contrib.auth.models import AbstractUser
from django.db import models

from .specialties import SpecialtyCode


class User(AbstractUser):
    class UserType(models.TextChoices):
        PATIENT = "PATIENT", "환자"
        HOSPITAL = "HOSPITAL", "병원"

    class Language(models.TextChoices):
        KOREAN = "ko", "한국어"
        ENGLISH = "en", "English"
        JAPANESE = "ja", "日本語"
        CHINESE = "zh", "中文"

    name = models.CharField(
        max_length=100,
    )

    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
    )

    preferred_language = models.CharField(
        max_length=10,
        choices=Language.choices,
        default=Language.KOREAN,
    )

    # 필수 동의
    terms_agreed = models.BooleanField(
        default=False,
    )

    privacy_agreed = models.BooleanField(
        default=False,
    )

    overseas_info_agreed = models.BooleanField(
        default=False,
    )

    overseas_transfer_agreed = models.BooleanField(
        default=False,
    )

    # 선택 동의
    marketing_agreed = models.BooleanField(
        default=False,
    )

    location_info_agreed = models.BooleanField(
        default=False,
    )


class PatientProfile(models.Model):
    patient_id = models.BigAutoField(
        primary_key=True,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="patient_profile",
    )

    passport_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    birth_date = models.DateField(
        null=True,
        blank=True,
    )

    nationality = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )

    phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    address = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    residence_country = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.user.name


class HospitalProfile(models.Model):
    hospital_id = models.BigAutoField(
        primary_key=True,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="hospital_profile",
    )

    country = models.CharField(
        max_length=50,
    )

    city = models.CharField(
        max_length=100,
    )

    address = models.CharField(
        max_length=255,
    )

    hospital_type = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    language_code = models.CharField(
        max_length=10,
        default="en",
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )

    phone = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    website = models.URLField(
        max_length=500,
        null=True,
        blank=True,
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    business_hours = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.user.name


class MedicalSpecialty(models.Model):
    hospital_specialty_id = models.BigAutoField(
        primary_key=True,
    )

    hospital = models.ForeignKey(
        HospitalProfile,
        on_delete=models.CASCADE,
        related_name="specialties",
    )

    specialty_code = models.CharField(
        max_length=30,
        choices=SpecialtyCode.choices,
        default=SpecialtyCode.CUSTOM,
    )

    specialty_name = models.CharField(
        max_length=100,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "hospital",
                    "specialty_name",
                ],
                name="unique_hospital_specialty",
            )
        ]

    def __str__(self):
        return (
            f"{self.hospital.user.name} "
            f"- {self.specialty_name}"
        )
