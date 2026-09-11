from django.db import models
from accounts.validators import coordinate_constraint, validate_latitude, validate_longitude
from .validation import (
    validate_weight, validate_score, validate_distance, validate_rank,
    validate_count, validate_recommendation_values,
)

from accounts.models import (
    HospitalProfile,
    PatientProfile,
    COUNTRY_CHOICES,
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
        validators=[validate_weight],
        default=50,
    )

    distance_weight = models.PositiveSmallIntegerField(
        validators=[validate_weight],
        default=50,
    )

    collaboration_weight = models.PositiveSmallIntegerField(
        validators=[validate_weight],
        default=50,
    )

    location_source = models.CharField(
        max_length=20,
        choices=LocationSource.choices,
        default=LocationSource.PROFILE,
    )

    search_country = models.CharField(
        max_length=2,
        choices=COUNTRY_CHOICES,
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
        validators=[validate_latitude],
        max_digits=10,
        decimal_places=7,
    )

    search_longitude = models.DecimalField(
        validators=[validate_longitude],
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
        constraints = [
            coordinate_constraint("match_search_coordinates_valid", "search_latitude", "search_longitude"),
            models.CheckConstraint(
                condition=models.Q(
                    specialty_weight__gte=0, specialty_weight__lte=100,
                    distance_weight__gte=0, distance_weight__lte=100,
                    collaboration_weight__gte=0, collaboration_weight__lte=100,
                ) & (
                    models.Q(specialty_weight__gt=0)
                    | models.Q(distance_weight__gt=0)
                    | models.Q(collaboration_weight__gt=0)
                ),
                name="match_weights_valid",
            ),
        ]


class HospitalRecommendation(models.Model):

    class SelectionSource(models.TextChoices):
        AI_RECOMMENDATION = "AI_RECOMMENDATION", "AI 추천"
        NETWORK = "NETWORK", "네트워크 병원"

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

    batch_number = models.PositiveSmallIntegerField(validators=[validate_rank])

    rank_number = models.PositiveSmallIntegerField(validators=[validate_rank])

    specialty_score = models.DecimalField(
        validators=[validate_score],
        max_digits=5,
        decimal_places=2,
    )

    distance_score = models.DecimalField(
        validators=[validate_score],
        max_digits=5,
        decimal_places=2,
    )

    collaboration_score = models.DecimalField(
        validators=[validate_score],
        max_digits=5,
        decimal_places=2,
    )

    total_score = models.DecimalField(
        validators=[validate_score],
        max_digits=5,
        decimal_places=2,
    )

    distance_km = models.DecimalField(
        validators=[validate_distance],
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    collaboration_count = models.PositiveIntegerField(
        validators=[validate_count],
        default=0,
    )

    is_selected = models.BooleanField(
        default=False,
    )

    selection_source = models.CharField(
        max_length=30,
        choices=SelectionSource.choices,
        default=SelectionSource.AI_RECOMMENDATION,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def save(self, *args, **kwargs):
        validate_recommendation_values({
            field: getattr(self, field) for field in (
                "specialty_score", "distance_score", "collaboration_score",
                "total_score", "distance_km", "batch_number", "rank_number",
                "collaboration_count",
            )
        })
        return super().save(*args, **kwargs)

    class Meta:
        db_table = "HOSPITAL_RECOMMENDATION"

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    specialty_score__gte=0, specialty_score__lte=100,
                    distance_score__gte=0, distance_score__lte=100,
                    collaboration_score__gte=0, collaboration_score__lte=100,
                    total_score__gte=0, total_score__lte=100,
                    batch_number__gte=1, batch_number__lte=32767,
                    rank_number__gte=1, rank_number__lte=32767,
                    collaboration_count__gte=0, collaboration_count__lte=2147483647,
                ),
                name="recommendation_numbers_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(distance_km__isnull=True) | models.Q(
                    distance_km__gte=0, distance_km__lte=99999999.99,
                ),
                name="recommendation_distance_valid",
            ),
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
