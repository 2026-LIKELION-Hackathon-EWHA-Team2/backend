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