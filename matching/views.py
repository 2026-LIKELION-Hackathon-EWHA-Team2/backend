from django.db import transaction
from django.db.models import Max, Q

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HospitalProfile, PatientProfile
from selfsymptoms.models import PatientSymptomCase

from .models import (
    HospitalMatchRequest,
    HospitalRecommendation,
)

from .serializers import (
    HospitalMatchConsentSerializer,
    HospitalMatchRequestSerializer,
    HospitalRecommendationSerializer,
    HospitalSimpleSerializer,
)

from .services import (
    calculate_collaboration_score,
    calculate_distance_km,
    calculate_distance_score,
    generate_recommendations,
    get_collaboration_count,
)


def _japan_hospitals():
    return (
        HospitalProfile.objects
        .filter(
            Q(country__iexact="JP")
            | Q(country__iexact="JAPAN")
        )
        .select_related("user")
        .prefetch_related("specialties")
    )


class NetworkHospitalListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            patient = PatientProfile.objects.get(user=request.user)
        except PatientProfile.DoesNotExist:
            return Response(
                {"detail": "환자 프로필이 존재하지 않습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        sort = request.query_params.get("sort", "distance")
        if sort not in {"distance", "collaboration"}:
            return Response(
                {"detail": "sort는 distance 또는 collaboration이어야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hospitals = []
        for hospital in _japan_hospitals():
            distance_km = None
            if (
                patient.latitude is not None
                and patient.longitude is not None
                and hospital.latitude is not None
                and hospital.longitude is not None
            ):
                distance_km = calculate_distance_km(
                    patient.latitude,
                    patient.longitude,
                    hospital.latitude,
                    hospital.longitude,
                )

            hospital_data = HospitalSimpleSerializer(hospital).data
            hospital_data["distance_km"] = distance_km
            hospital_data["collaboration_count"] = (
                get_collaboration_count(hospital)
            )
            hospitals.append(hospital_data)

        if sort == "distance":
            hospitals.sort(
                key=lambda item: (
                    item["distance_km"] is None,
                    item["distance_km"] or 0,
                    item["name"],
                )
            )
        else:
            hospitals.sort(
                key=lambda item: (
                    -item["collaboration_count"],
                    item["distance_km"] is None,
                    item["distance_km"] or 0,
                    item["name"],
                )
            )

        return Response(hospitals, status=status.HTTP_200_OK)


class NetworkHospitalDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hospital_id):
        try:
            patient = PatientProfile.objects.get(user=request.user)
        except PatientProfile.DoesNotExist:
            return Response(
                {"detail": "환자 프로필이 존재하지 않습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            hospital = _japan_hospitals().get(hospital_id=hospital_id)
        except HospitalProfile.DoesNotExist:
            return Response(
                {"detail": "네트워크 병원을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        distance_km = None
        if (
            patient.latitude is not None
            and patient.longitude is not None
            and hospital.latitude is not None
            and hospital.longitude is not None
        ):
            distance_km = calculate_distance_km(
                patient.latitude,
                patient.longitude,
                hospital.latitude,
                hospital.longitude,
            )

        data = HospitalSimpleSerializer(hospital).data
        data["distance_km"] = distance_km
        data["collaboration_count"] = get_collaboration_count(hospital)
        return Response(data, status=status.HTTP_200_OK)


class NetworkHospitalSelectView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, hospital_id):
        try:
            patient = PatientProfile.objects.get(user=request.user)
        except PatientProfile.DoesNotExist:
            return Response(
                {"detail": "환자 프로필이 존재하지 않습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            symptom_case = PatientSymptomCase.objects.select_for_update().get(
                symptom_case_id=request.data.get("symptom_case_id"),
                patient=patient,
            )
        except PatientSymptomCase.DoesNotExist:
            return Response(
                {"detail": "증상 케이스를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if symptom_case.status not in {
            PatientSymptomCase.Status.SUBMITTED,
            PatientSymptomCase.Status.MATCHING,
            PatientSymptomCase.Status.HOSPITAL_SELECTED,
        }:
            return Response(
                {"detail": "현재 상태에서는 병원을 선택할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            hospital = _japan_hospitals().get(hospital_id=hospital_id)
        except HospitalProfile.DoesNotExist:
            return Response(
                {"detail": "네트워크 병원을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if patient.latitude is None or patient.longitude is None:
            return Response(
                {"detail": "환자 프로필에 위치 좌표를 등록해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        match_request = (
            HospitalMatchRequest.objects
            .select_for_update()
            .filter(
                symptom_case=symptom_case,
                patient=patient,
                status__in=[
                    HospitalMatchRequest.Status.COMPLETED,
                    HospitalMatchRequest.Status.SELECTED,
                ],
            )
            .order_by("-created_at")
            .first()
        )

        if match_request is None:
            match_request = HospitalMatchRequest.objects.create(
                symptom_case=symptom_case,
                patient=patient,
                location_source=HospitalMatchRequest.LocationSource.PROFILE,
                search_country="JP",
                search_city=patient.city,
                search_address=patient.address,
                search_latitude=patient.latitude,
                search_longitude=patient.longitude,
                status=HospitalMatchRequest.Status.COMPLETED,
            )

        distance_km = None
        distance_score = 0
        if hospital.latitude is not None and hospital.longitude is not None:
            distance_km = calculate_distance_km(
                patient.latitude,
                patient.longitude,
                hospital.latitude,
                hospital.longitude,
            )
            distance_score = calculate_distance_score(distance_km)

        collaboration_count = get_collaboration_count(hospital)
        collaboration_score = calculate_collaboration_score(hospital)
        next_rank = (
            match_request.recommendations.aggregate(Max("rank_number"))[
                "rank_number__max"
            ]
            or 0
        ) + 1

        recommendation, created = HospitalRecommendation.objects.get_or_create(
            match_request=match_request,
            hospital=hospital,
            defaults={
                "batch_number": 1,
                "rank_number": next_rank,
                "specialty_score": 0,
                "distance_score": distance_score,
                "collaboration_score": collaboration_score,
                "collaboration_count": collaboration_count,
                "total_score": 0,
                "distance_km": distance_km,
                "selection_source": (
                    HospitalRecommendation.SelectionSource.NETWORK
                ),
            },
        )
        if not created:
            recommendation.selection_source = (
                HospitalRecommendation.SelectionSource.NETWORK
            )
            recommendation.distance_km = distance_km
            recommendation.distance_score = distance_score
            recommendation.collaboration_count = collaboration_count
            recommendation.collaboration_score = collaboration_score
            recommendation.save(update_fields=[
                "selection_source",
                "distance_km",
                "distance_score",
                "collaboration_count",
                "collaboration_score",
            ])

        match_request.recommendations.update(is_selected=False)
        recommendation.is_selected = True
        recommendation.save(update_fields=["is_selected"])

        match_request.status = HospitalMatchRequest.Status.SELECTED
        match_request.personal_information_provision_agreed = False
        match_request.information_items_purpose_confirmed = False
        match_request.medical_consultation_use_agreed = False
        match_request.withdrawal_right_confirmed = False
        match_request.agreed_at = None
        match_request.save()

        symptom_case.status = PatientSymptomCase.Status.HOSPITAL_SELECTED
        symptom_case.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "message": "협진 상대 병원이 선택되었습니다.",
                "match_request_id": match_request.match_request_id,
                "symptom_case_id": symptom_case.symptom_case_id,
                "recommendation_id": recommendation.recommendation_id,
                "partner_hospital_id": hospital.hospital_id,
                "partner_hospital_user_id": hospital.user_id,
                "partner_hospital_name": hospital.user.name,
                "selection_source": recommendation.selection_source,
            },
            status=status.HTTP_200_OK,
        )


# ==========================================
# 1. 병원 매칭 요청 생성 + AI 추천 실행
# ==========================================

class HospitalMatchRequestCreateView(APIView):

    permission_classes = [
        IsAuthenticated,
    ]

    def post(self, request):

        # -------------------------
        # 로그인한 환자 확인
        # -------------------------

        try:
            patient = PatientProfile.objects.get(
                user=request.user
            )

        except PatientProfile.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "환자 프로필이 존재하지 않습니다."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # -------------------------
        # 요청 데이터 검증
        # -------------------------

        serializer = (
            HospitalMatchRequestSerializer(
                data=request.data,
                context={
                    "request": request,
                    "patient": patient,
                },
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        symptom_case = (
            serializer.validated_data[
                "symptom_case"
            ]
        )

        # -------------------------
        # 본인의 증상 케이스인지 확인
        # -------------------------

        if (
            symptom_case.patient_id
            != patient.patient_id
        ):
            return Response(
                {
                    "detail": (
                        "본인의 증상 케이스만 "
                        "매칭에 사용할 수 있습니다."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # -------------------------
        # 작성 완료된 케이스인지 확인
        # -------------------------

        if (
            symptom_case.status
            != PatientSymptomCase.Status.SUBMITTED
        ):
            return Response(
                {
                    "detail": (
                        "작성 완료된 증상 케이스만 "
                        "병원 매칭에 사용할 수 있습니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -------------------------
        # 매칭 요청 생성
        # -------------------------

        match_request = serializer.save(
            patient=patient,
        )

        # 증상 케이스 상태 변경
        symptom_case.status = (
            PatientSymptomCase.Status.MATCHING
        )

        symptom_case.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        # -------------------------
        # AI 분석 + 추천 병원 생성
        # -------------------------

        try:

            recommendations = (
                generate_recommendations(
                    match_request
                )
            )

        except Exception as error:

            # 분석 실패 시 다시 대기 상태
            match_request.status = (
                HospitalMatchRequest
                .Status
                .PENDING
            )

            match_request.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            symptom_case.status = (
                PatientSymptomCase.Status.SUBMITTED
            )
            symptom_case.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "detail": (
                        "병원 추천 분석 중 "
                        "오류가 발생했습니다."
                    ),
                    "error": str(error),
                },
                status=(
                    status.HTTP_502_BAD_GATEWAY
                ),
            )

        # -------------------------
        # 결과 반환
        # -------------------------

        match_request_data = (
            HospitalMatchRequestSerializer(
                match_request
            ).data
        )

        recommendation_data = (
            HospitalRecommendationSerializer(
                recommendations,
                many=True,
            ).data
        )

        return Response(
            {
                "match_request":
                    match_request_data,

                "recommendations":
                    recommendation_data,
            },
            status=status.HTTP_201_CREATED,
        )


# ==========================================
# 2. 매칭 요청 상세 조회
# ==========================================

class HospitalMatchRequestDetailView(
    APIView
):

    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        match_request_id,
    ):

        try:
            patient = PatientProfile.objects.get(
                user=request.user
            )

        except PatientProfile.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "환자 프로필이 존재하지 않습니다."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            match_request = (
                HospitalMatchRequest.objects
                .get(
                    match_request_id=(
                        match_request_id
                    ),
                    patient=patient,
                )
            )

        except HospitalMatchRequest.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "매칭 요청을 찾을 수 없습니다."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = (
            HospitalMatchRequestSerializer(
                match_request
            )
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


# ==========================================
# 3. 추천 병원 목록 조회
# ==========================================

class HospitalRecommendationListView(APIView):

    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        match_request_id,
    ):

        try:
            patient = PatientProfile.objects.get(
                user=request.user
            )

        except PatientProfile.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "환자 프로필이 존재하지 않습니다."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            match_request = (
                HospitalMatchRequest.objects
                .get(
                    match_request_id=match_request_id,
                    patient=patient,
                )
            )

        except HospitalMatchRequest.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "매칭 요청을 찾을 수 없습니다."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        sort = request.query_params.get(
            "sort",
            "recommended",
        )

        ordering_map = {
            "recommended": (
                "rank_number",
            ),
            "distance": (
                "distance_km",
                "rank_number",
            ),
            "collaboration": (
                "-collaboration_count",
                "rank_number",
            ),
            "diagnosis": (
                "-specialty_score",
                "rank_number",
            ),
        }

        if sort not in ordering_map:
            return Response(
                {
                    "detail": (
                        "sort는 recommended, distance, "
                        "collaboration, diagnosis 중 하나여야 합니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        recommendations = (
            match_request
            .recommendations
            .select_related(
                "hospital",
                "hospital__user",
            )
            .prefetch_related(
                "hospital__specialties",
            )
            .order_by(
                *ordering_map[sort]
            )
        )

        serializer = HospitalRecommendationSerializer(
            recommendations,
            many=True,
        )

        return Response(
            {
                "match_request_id":
                    match_request.match_request_id,

                "required_specialty":
                    match_request.required_specialty,

                "required_specialty_code":
                    match_request.required_specialty_code,

                "recommendations":
                    serializer.data,
            },
            status=status.HTTP_200_OK,
        )


# ==========================================
# 4. 추천 병원 선택
# ==========================================

class HospitalRecommendationSelectView(
    APIView
):

    permission_classes = [
        IsAuthenticated,
    ]

    @transaction.atomic
    def post(
        self,
        request,
        recommendation_id,
    ):

        # -------------------------
        # 환자 확인
        # -------------------------

        try:
            patient = PatientProfile.objects.get(
                user=request.user
            )

        except PatientProfile.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "환자 프로필이 존재하지 않습니다."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # -------------------------
        # 추천 정보 조회
        # -------------------------

        try:
            recommendation = (
                HospitalRecommendation.objects
                .select_related(
                    "hospital",
                    "match_request",
                    "match_request__symptom_case",
                )
                .get(
                    recommendation_id=(
                        recommendation_id
                    )
                )
            )

        except HospitalRecommendation.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "추천 병원을 찾을 수 없습니다."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        match_request = (
            recommendation.match_request
        )

        # -------------------------
        # 본인의 매칭 요청인지 확인
        # -------------------------

        if (
            match_request.patient_id
            != patient.patient_id
        ):
            return Response(
                {
                    "detail": (
                        "본인의 매칭 요청에서만 "
                        "병원을 선택할 수 있습니다."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        #매칭 요청 상태 확인
        allowed_statuses = {
            HospitalMatchRequest.Status.COMPLETED,
            HospitalMatchRequest.Status.SELECTED,
        }

        if match_request.status not in allowed_statuses:
            return Response(
                {
                    "detail": (
                        "현재 상태에서는 추천 병원을 "
                        "선택할 수 없습니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # -------------------------
        # 기존 선택 병원 초기화
        # -------------------------

        match_request.recommendations.update(
            is_selected=False
        )

        # -------------------------
        # 현재 병원 선택
        # -------------------------

        recommendation.is_selected = True

        recommendation.save(
            update_fields=[
                "is_selected",
            ]
        )

        # -------------------------
        # 매칭 요청 상태 변경
        # -------------------------

        match_request.status = (
            HospitalMatchRequest
            .Status
            .SELECTED
        )
        match_request.personal_information_provision_agreed = False
        match_request.information_items_purpose_confirmed = False
        match_request.medical_consultation_use_agreed = False
        match_request.withdrawal_right_confirmed = False
        match_request.agreed_at = None

        match_request.save(
            update_fields=[
                "status",
                "personal_information_provision_agreed",
                "information_items_purpose_confirmed",
                "medical_consultation_use_agreed",
                "withdrawal_right_confirmed",
                "agreed_at",
                "updated_at",
            ]
        )

        # -------------------------
        # 증상 케이스 상태 변경
        # -------------------------

        symptom_case = (
            match_request.symptom_case
        )

        symptom_case.status = (
            PatientSymptomCase
            .Status
            .HOSPITAL_SELECTED
        )

        symptom_case.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        # -------------------------
        # partner_hospital_id 반환
        # -------------------------

        return Response(
            {
                "message": (
                    "협진 상대 병원이 "
                    "선택되었습니다."
                ),

                "match_request_id":
                    match_request.match_request_id,

                "symptom_case_id":
                    symptom_case.symptom_case_id,

                "recommendation_id":
                    recommendation.recommendation_id,

                "partner_hospital_id":
                    recommendation
                    .hospital
                    .hospital_id,

                "partner_hospital_user_id":
                    recommendation
                    .hospital
                    .user_id,

                "partner_hospital_name":
                    recommendation
                    .hospital
                    .user
                    .name,
            },
            status=status.HTTP_200_OK,
        )


class HospitalMatchConsentView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, match_request_id):
        try:
            patient = PatientProfile.objects.get(user=request.user)
        except PatientProfile.DoesNotExist:
            return Response(
                {"detail": "환자 프로필이 존재하지 않습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            match_request = HospitalMatchRequest.objects.get(
                match_request_id=match_request_id,
                patient=patient,
            )
        except HospitalMatchRequest.DoesNotExist:
            return Response(
                {"detail": "매칭 요청을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = HospitalMatchConsentSerializer(
            match_request,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        match_request = serializer.save()

        return Response(
            HospitalMatchRequestSerializer(match_request).data,
            status=status.HTTP_200_OK,
        )
