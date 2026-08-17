from math import (
    asin,
    cos,
    radians,
    sin,
    sqrt,
)

from accounts.models import HospitalProfile
from accounts.specialties import SpecialtyCode, normalize_specialty_name
from cases.models import MedicalCase

from .ai_service import analyze_required_specialty
from .models import HospitalRecommendation


# ==========================================
# 1. selfsymptoms -> 필요 진료과 결정
# ==========================================

def determine_required_specialty(
    symptom_case,
):
    """
    OpenAI를 이용하여
    증상 케이스의 필요 진료과를 분석한다.
    """

    return analyze_required_specialty(
        symptom_case
    )
# ==========================================
# 2. GPS 거리 계산
# ==========================================

def calculate_distance_km(
    latitude1,
    longitude1,
    latitude2,
    longitude2,
):

    latitude1 = radians(
        float(latitude1)
    )

    longitude1 = radians(
        float(longitude1)
    )

    latitude2 = radians(
        float(latitude2)
    )

    longitude2 = radians(
        float(longitude2)
    )

    delta_latitude = (
        latitude2 - latitude1
    )

    delta_longitude = (
        longitude2 - longitude1
    )

    a = (
        sin(delta_latitude / 2) ** 2
        + cos(latitude1)
        * cos(latitude2)
        * sin(delta_longitude / 2) ** 2
    )

    c = 2 * asin(
        sqrt(a)
    )

    earth_radius_km = 6371

    return earth_radius_km * c


# ==========================================
# 3. 전문분야 일치 점수
# ==========================================

def calculate_specialty_score(
    required_specialty,
    required_specialty_code,
    hospital,
):
    """
    required_specialty:
        selfsymptoms 분석 결과

    hospital:
        HospitalProfile 객체

    병원이 가지고 있는 MedicalSpecialty와 비교한다.
    """

    hospital_specialties = list(hospital.specialties.all())

    if (
        required_specialty_code
        and required_specialty_code != SpecialtyCode.CUSTOM
        and any(
            specialty.specialty_code == required_specialty_code
            for specialty in hospital_specialties
        )
    ):
        return 100

    normalized_required_specialty = normalize_specialty_name(
        required_specialty
    )
    if any(
        normalize_specialty_name(specialty.specialty_name)
        == normalized_required_specialty
        for specialty in hospital_specialties
    ):
        return 100

    return 0


# ==========================================
# 4. 거리 점수
# ==========================================

def calculate_distance_score(
    distance_km,
):
    if distance_km <= 2:
        return 100

    if distance_km <= 5:
        return 90

    if distance_km <= 10:
        return 80

    if distance_km <= 20:
        return 60

    if distance_km <= 50:
        return 40

    return 20


# ==========================================
# 5. 협진 경험
# ==========================================

def get_collaboration_count(
    hospital,
):
    """
    해당 병원이 partner_hospital로 연결되어
    실제 TRANSFERRED까지 완료된 MedicalCase 수를
    협진 경험으로 사용한다.

    MedicalCase.partner_hospital은 User FK이므로
    hospital.user를 사용한다.
    """

    return (
        MedicalCase.objects
        .filter(
            partner_hospital=hospital.user,
            status=MedicalCase.Status.TRANSFERRED,
        )
        .count()
    )


def calculate_collaboration_score(
    hospital,
):
    count = get_collaboration_count(
        hospital
    )

    if count >= 10:
        return 100

    if count >= 5:
        return 80

    if count >= 1:
        return 60

    return 20


# ==========================================
# 6. 총점
# ==========================================

def calculate_total_score(
    specialty_score,
    distance_score,
    collaboration_score,
    specialty_weight,
    distance_weight,
    collaboration_weight,
):

    total_weight = (
        specialty_weight
        + distance_weight
        + collaboration_weight
    )

    if total_weight == 0:
        return 0

    score = (
        specialty_score
        * specialty_weight

        + distance_score
        * distance_weight

        + collaboration_score
        * collaboration_weight
    ) / total_weight

    return round(
        score,
        2,
    )


# ==========================================
# 7. 추천 병원 생성
# ==========================================

def generate_recommendations(
    match_request,
):

    # selfsymptoms case 분석
    required_specialty_result = (
        determine_required_specialty(
            match_request.symptom_case
        )
    )

    if required_specialty_result is None:
        raise ValueError(
            "필요 진료과를 분석할 수 없습니다."
        )

    required_specialty = required_specialty_result[
        "specialty_name"
    ]
    required_specialty_code = required_specialty_result[
        "specialty_code"
    ]

    match_request.required_specialty = (
        required_specialty
    )
    match_request.required_specialty_code = (
        required_specialty_code
    )

    match_request.status = (
        match_request.Status.ANALYZING
    )

    match_request.save(
        update_fields=[
            "required_specialty",
            "required_specialty_code",
            "status",
            "updated_at",
        ]
    )

    # 병원 계정만 대상으로 함
    hospitals = (
        HospitalProfile.objects
        .filter(
            user__user_type="HOSPITAL"
        )
        .select_related(
            "user"
        )
        .prefetch_related(
            "specialties"
        )
    )

    results = []

    for hospital in hospitals:

        # GPS 정보 없는 병원 제외
        if (
            hospital.latitude is None
            or hospital.longitude is None
        ):
            continue

        # 환자가 검색한 국가와 다른 병원 제외
        if (
            match_request.search_country
            and hospital.country
            != match_request.search_country
        ):
            continue

        distance_km = calculate_distance_km(
            match_request.search_latitude,
            match_request.search_longitude,
            hospital.latitude,
            hospital.longitude,
        )

        specialty_score = (
            calculate_specialty_score(
                required_specialty,
                required_specialty_code,
                hospital,
            )
        )

        distance_score = (
            calculate_distance_score(
                distance_km
            )
        )

        collaboration_score = (
            calculate_collaboration_score(
                hospital
            )
        )

        total_score = (
            calculate_total_score(
                specialty_score,
                distance_score,
                collaboration_score,
                match_request.specialty_weight,
                match_request.distance_weight,
                match_request.collaboration_weight,
            )
        )

        collaboration_count = (
            get_collaboration_count(
                hospital
            )
        )

        results.append(
            {
                "hospital": hospital,

                "distance_km":
                    distance_km,

                "specialty_score":
                    specialty_score,

                "distance_score":
                    distance_score,

                "collaboration_score":
                    collaboration_score,

                "collaboration_count":
                    collaboration_count,

                "total_score":
                    total_score,
            }
        )

    # AI 추천 리스트 기본 순서
    # 최종 가중 총점 높은 병원부터
    results.sort(
        key=lambda item: item[
            "total_score"
        ],
        reverse=True,
    )

    # 동일 요청을 재분석할 경우 기존 추천 제거
    match_request.recommendations.all().delete()

    recommendations = []

    # 최대 20개
    for rank, result in enumerate(
        results[:20],
        start=1,
    ):

        recommendation = (
            HospitalRecommendation.objects
            .create(
                match_request=match_request,

                hospital=result[
                    "hospital"
                ],

                batch_number=(
                    (rank - 1) // 5
                ) + 1,

                rank_number=rank,

                specialty_score=result[
                    "specialty_score"
                ],

                distance_score=result[
                    "distance_score"
                ],

                collaboration_score=result[
                    "collaboration_score"
                ],

                collaboration_count=result[
                    "collaboration_count"
                ], 

                total_score=result[
                    "total_score"
                ],

                distance_km=round(
                    result[
                        "distance_km"
                    ],
                    2,
                ),
            )
        )

        recommendations.append(
            recommendation
        )

    match_request.status = (
        match_request.Status.COMPLETED
    )

    match_request.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return recommendations
