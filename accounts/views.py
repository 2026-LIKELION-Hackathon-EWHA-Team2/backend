from django.http import HttpRequest

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    HospitalProfile,
    PatientProfile,
)
from .serializers import (
    HospitalProfileSerializer,
    HospitalSignUpSerializer,
    PatientProfileSerializer,
    PatientSignUpSerializer,
    UserLoginSerializer,
)
from .specialties import MAX_SPECIALTY_SELECTIONS, SpecialtyCode


class MedicalSpecialtyOptionsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "specialties": [
                    {
                        "specialty_code": code,
                        "specialty_name": label,
                        "requires_custom_name": (
                            code == SpecialtyCode.CUSTOM
                        ),
                    }
                    for code, label in SpecialtyCode.choices
                ],
                "max_selections": MAX_SPECIALTY_SELECTIONS,
            },
            status=status.HTTP_200_OK,
        )


class PatientSignUpView(APIView):
    def post(
        self,
        request: HttpRequest,
        format=None,
    ):
        serializer = PatientSignUpSerializer(
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class HospitalSignUpView(APIView):
    def post(
        self,
        request: HttpRequest,
        format=None,
    ):
        serializer = HospitalSignUpSerializer(
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class LoginView(APIView):
    def post(
        self,
        request: HttpRequest,
        format=None,
    ):
        serializer = UserLoginSerializer(
            data=request.data
        )

        if serializer.is_valid():
            return Response(
                serializer.validated_data,
                status=status.HTTP_200_OK,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class LogoutView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

    def post(
        self,
        request: HttpRequest,
        format=None,
    ):
        refresh_token = request.data.get(
            "refresh"
        )

        if not refresh_token:
            return Response(
                {
                    "detail": (
                        "refresh token이 필요합니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(
                refresh_token
            )

            token.blacklist()

            return Response(
                {
                    "detail": "로그아웃되었습니다."
                },
                status=status.HTTP_200_OK,
            )

        except TokenError:
            return Response(
                {
                    "detail": (
                        "유효하지 않거나 만료된 "
                        "refresh token입니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class PatientProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != "PATIENT":
            return Response(
                {
                    "detail": "환자 계정만 접근할 수 있습니다."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            profile = request.user.patient_profile

        except PatientProfile.DoesNotExist:
            return Response(
                {
                    "detail": "환자 프로필이 존재하지 않습니다."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PatientProfileSerializer(
            profile
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if request.user.user_type != "PATIENT":
            return Response(
                {
                    "detail": "환자 계정만 접근할 수 있습니다."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if hasattr(
            request.user,
            "patient_profile",
        ):
            return Response(
                {
                    "detail": "이미 환자 프로필이 존재합니다."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PatientProfileSerializer(
            data=request.data,
        )

        if serializer.is_valid():
            serializer.save(
                user=request.user,
            )

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    def patch(self, request):
        if request.user.user_type != "PATIENT":
            return Response(
                {
                    "detail": "환자 계정만 접근할 수 있습니다."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            profile = request.user.patient_profile

        except PatientProfile.DoesNotExist:
            return Response(
                {
                    "detail": "환자 프로필이 존재하지 않습니다."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PatientProfileSerializer(
            profile,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                serializer.data,
                status=status.HTTP_200_OK,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class HospitalProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != "HOSPITAL":
            return Response(
                {
                    "detail": "병원 계정만 접근할 수 있습니다."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            profile = request.user.hospital_profile

        except HospitalProfile.DoesNotExist:
            return Response(
                {
                    "detail": "병원 프로필이 존재하지 않습니다."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = HospitalProfileSerializer(
            profile
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if request.user.user_type != "HOSPITAL":
            return Response(
                {
                    "detail": "병원 계정만 접근할 수 있습니다."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if hasattr(
            request.user,
            "hospital_profile",
        ):
            return Response(
                {
                    "detail": "이미 병원 프로필이 존재합니다."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = HospitalProfileSerializer(
            data=request.data,
        )

        if serializer.is_valid():
            serializer.save(
                user=request.user,
            )

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    def patch(self, request):
        if request.user.user_type != "HOSPITAL":
            return Response(
                {
                    "detail": "병원 계정만 접근할 수 있습니다."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            profile = request.user.hospital_profile

        except HospitalProfile.DoesNotExist:
            return Response(
                {
                    "detail": "병원 프로필이 존재하지 않습니다."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = HospitalProfileSerializer(
            profile,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                serializer.data,
                status=status.HTTP_200_OK,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class HospitalListView(APIView):
    """
    회원가입된 병원 목록 조회 API

    GET /accounts/hospitals/
    """

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        hospitals = (
            HospitalProfile.objects
            .select_related("user")
            .prefetch_related("specialties")
            .all()
            .order_by("user__name")
        )

        serializer = HospitalProfileSerializer(
            hospitals,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
