from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class UserType(models.TextChoices):
        PATIENT = "PATIENT", "환자"
        HOSPITAL = "HOSPITAL", "병원"

    name = models.CharField(max_length=100)

    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
    )

    # 필수 동의
    terms_agreed = models.BooleanField(default=False)
    privacy_agreed = models.BooleanField(default=False)
    overseas_info_agreed = models.BooleanField(default=False)

    # 선택 동의
    marketing_agreed = models.BooleanField(default=False)


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

    phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    # 현재 기능에서는 사용하지 않음
    email = models.EmailField(
        null=True,
        blank=True,
    )

    residence_country = models.CharField(
        max_length=50,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.user.name