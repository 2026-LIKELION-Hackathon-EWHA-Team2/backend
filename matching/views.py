from django.db import transaction

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import PatientProfile
from selfsymptoms.models import PatientSymptomCase

from .models import (
    HospitalMatchRequest,
    HospitalRecommendation,
)

from .serializers import (
    HospitalMatchConsentSerializer,
    HospitalMatchRequestSerializer,
    HospitalRecommendationSerializer,
)

from .services import generate_recommendations


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

class HospitalRecommendationListView(
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

        recommendations = (
            match_request
            .recommendations
            .select_related(
                "hospital",
                "hospital__user",
            )
            .prefetch_related(
                "hospital__specialties"
            )
            .order_by(
                "rank_number"
            )
        )

        serializer = (
            HospitalRecommendationSerializer(
                recommendations,
                many=True,
            )
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
