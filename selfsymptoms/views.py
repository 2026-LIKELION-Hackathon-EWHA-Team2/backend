from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from accounts.models import PatientProfile

from .models import (
    PatientSymptomCase,
    PatientSymptomImage,
)
from .serializers import (
    PatientSymptomCaseSerializer,
    PatientSymptomImageSerializer,
)


class PatientSymptomCaseViewSet(viewsets.ModelViewSet):
    """
    개인 부작용 상태 기록 API

    GET    /symptom-cases/
    POST   /symptom-cases/
    GET    /symptom-cases/{id}/
    PATCH  /symptom-cases/{id}/
    DELETE /symptom-cases/{id}/
    """

    serializer_class = PatientSymptomCaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_patient_profile(self):
        """
        현재 로그인한 사용자의 PatientProfile을 반환한다.
        환자 계정이 아니거나 환자 프로필이 없으면 오류를 발생시킨다.
        """

        user = self.request.user

        if user.user_type != user.UserType.PATIENT:
            raise PermissionDenied(
                "환자 계정만 개인 증상 기록 기능을 사용할 수 있습니다."
            )

        try:
            return user.patient_profile
        except PatientProfile.DoesNotExist:
            raise ValidationError(
                {
                    "patient_profile": (
                        "환자 프로필이 존재하지 않습니다."
                    )
                }
            )

    def get_queryset(self):
        """
        로그인한 환자의 증상 기록만 조회한다.
        """

        if not self.request.user.is_authenticated:
            return PatientSymptomCase.objects.none()

        try:
            patient = self.request.user.patient_profile
        except PatientProfile.DoesNotExist:
            return PatientSymptomCase.objects.none()

        return (
            PatientSymptomCase.objects
            .filter(patient=patient)
            .select_related(
                "patient",
                "patient__user",
            )
            .prefetch_related(
                "images",
                "areas",
                "symptom_types",
            )
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        """
        serializer의 create()에서 사용할 patient를 전달한다.
        """

        context = super().get_serializer_context()

        if self.request.method == "POST":
            context["patient"] = self.get_patient_profile()

        return context

    def perform_update(self, serializer):
        """
        자신의 증상 기록만 수정할 수 있도록 확인한다.
        """

        symptom_case = self.get_object()
        patient = self.get_patient_profile()

        if symptom_case.patient_id != patient.patient_id:
            raise PermissionDenied(
                "본인의 증상 기록만 수정할 수 있습니다."
            )

        serializer.save()

    def perform_destroy(self, instance):
        """
        자신의 증상 기록만 삭제할 수 있도록 확인한다.
        """

        patient = self.get_patient_profile()

        if instance.patient_id != patient.patient_id:
            raise PermissionDenied(
                "본인의 증상 기록만 삭제할 수 있습니다."
            )

        instance.delete()


class PatientSymptomImageViewSet(viewsets.ModelViewSet):
    """
    증상 사진 API

    사진 업로드는 multipart/form-data 형식으로 요청한다.

    GET    /symptom-images/
    POST   /symptom-images/
    GET    /symptom-images/{id}/
    PATCH  /symptom-images/{id}/
    DELETE /symptom-images/{id}/
    """

    serializer_class = PatientSymptomImageSerializer
    permission_classes = [permissions.IsAuthenticated]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    def get_patient_profile(self):
        user = self.request.user

        if user.user_type != user.UserType.PATIENT:
            raise PermissionDenied(
                "환자 계정만 증상 사진을 등록할 수 있습니다."
            )

        try:
            return user.patient_profile
        except PatientProfile.DoesNotExist:
            raise ValidationError(
                {
                    "patient_profile": (
                        "환자 프로필이 존재하지 않습니다."
                    )
                }
            )

    def get_queryset(self):
        """
        로그인한 환자의 증상 사진만 조회한다.
        """

        if not self.request.user.is_authenticated:
            return PatientSymptomImage.objects.none()

        try:
            patient = self.request.user.patient_profile
        except PatientProfile.DoesNotExist:
            return PatientSymptomImage.objects.none()

        return (
            PatientSymptomImage.objects
            .filter(symptom_case__patient=patient)
            .select_related(
                "symptom_case",
                "symptom_case__patient",
            )
            .order_by(
                "symptom_case_id",
                "display_order",
            )
        )

    def create(self, request, *args, **kwargs):
        """
        증상 케이스 ID와 사진 파일을 받아 사진을 등록한다.
        """

        patient = self.get_patient_profile()

        symptom_case_id = request.data.get("symptom_case")

        if not symptom_case_id:
            return Response(
                {
                    "symptom_case": (
                        "증상 기록 ID를 입력해야 합니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        symptom_case = get_object_or_404(
            PatientSymptomCase,
            symptom_case_id=symptom_case_id,
        )

        if symptom_case.patient_id != patient.patient_id:
            raise PermissionDenied(
                "본인의 증상 기록에만 사진을 등록할 수 있습니다."
            )

        if symptom_case.images.count() >= 6:
            return Response(
                {
                    "image": (
                        "한 증상 기록에는 사진을 "
                        "최대 6장까지 등록할 수 있습니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(
            raise_exception=True,
        )

        serializer.save(
            symptom_case=symptom_case,
        )

        headers = self.get_success_headers(
            serializer.data,
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def perform_update(self, serializer):
        """
        본인이 등록한 사진만 수정할 수 있다.
        """

        symptom_image = self.get_object()
        patient = self.get_patient_profile()

        if (
            symptom_image.symptom_case.patient_id
            != patient.patient_id
        ):
            raise PermissionDenied(
                "본인의 증상 사진만 수정할 수 있습니다."
            )

        # 사진 수정 과정에서 다른 증상 케이스로
        # 옮기는 것을 방지한다.
        serializer.save(
            symptom_case=symptom_image.symptom_case,
        )

    def perform_destroy(self, instance):
        """
        본인이 등록한 사진만 삭제할 수 있다.
        """

        patient = self.get_patient_profile()

        if (
            instance.symptom_case.patient_id
            != patient.patient_id
        ):
            raise PermissionDenied(
                "본인의 증상 사진만 삭제할 수 있습니다."
            )

        instance.delete()