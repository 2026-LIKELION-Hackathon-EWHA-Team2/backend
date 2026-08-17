from django.db import models

from accounts.models import (
    HospitalProfile,
    PatientProfile,
)
from accounts.specialties import SpecialtyCode

from selfsymptoms.models import PatientSymptomCase


class HospitalMatchRequest(models.Model):

    class LocationSource(models.TextChoices):
        PROFILE = "PROFILE", "프로필 위치"
        CUSTOM = "CUSTOM", "직접 지정"

    class Status(models.TextChoices):
        PENDING = "PENDING", "대기"
        ANALYZING = "ANALYZING", "분석 중"
        COMPLETED = "COMPLETED", "분석 완료"
        SELECTED = "SELECTED", "병원 선택"
        CANCELLED = "CANCELLED", "취소"

    match_request_id = models.BigAutoField(
        primary_key=True,
    )

    symptom_case = models.ForeignKey(
        PatientSymptomCase,
        on_delete=models.CASCADE,
        related_name="match_requests",
    )

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="match_requests",
    )

    # selfsymptoms 분석 결과
    required_specialty = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    required_specialty_code = models.CharField(
        max_length=30,
        choices=SpecialtyCode.choices,
        null=True,
        blank=True,
    )

    specialty_weight = models.PositiveSmallIntegerField(
        default=50,
    )

    distance_weight = models.PositiveSmallIntegerField(
        default=50,
    )

    collaboration_weight = models.PositiveSmallIntegerField(
        default=50,
    )

    location_source = models.CharField(
        max_length=20,
        choices=LocationSource.choices,
        default=LocationSource.PROFILE,
    )

    search_country = models.CharField(
        max_length=50,
    )

    search_city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    search_address = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    search_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
    )

    search_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
    )

    personal_information_provision_agreed = models.BooleanField(
        default=False,
    )
    information_items_purpose_confirmed = models.BooleanField(
        default=False,
    )
    medical_consultation_use_agreed = models.BooleanField(
        default=False,
    )
    withdrawal_right_confirmed = models.BooleanField(
        default=False,
    )
    agreed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "HOSPITAL_MATCH_REQUEST"


class HospitalRecommendation(models.Model):

    recommendation_id = models.BigAutoField(
        primary_key=True,
    )

    match_request = models.ForeignKey(
        HospitalMatchRequest,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )

    hospital = models.ForeignKey(
        HospitalProfile,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )

    batch_number = models.PositiveSmallIntegerField()

    rank_number = models.PositiveSmallIntegerField()

    specialty_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    distance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    collaboration_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    total_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    distance_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    collaboration_count = models.PositiveIntegerField(
        default=0,
    )

    is_selected = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "HOSPITAL_RECOMMENDATION"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "match_request",
                    "hospital",
                ],
                name="unique_recommended_hospital",
            ),

            models.UniqueConstraint(
                fields=[
                    "match_request",
                    "rank_number",
                ],
                name="unique_recommendation_rank",
            ),
        ]
