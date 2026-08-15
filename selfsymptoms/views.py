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
    """

    serializer_class = PatientSymptomCaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    def get_patient_profile(self):
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
                "diagnosed_hospital",
                "diagnosed_hospital__user",
                "diagnosis_analysis",
            )
            .prefetch_related(
                "images",
                "areas",
                "symptom_types",
            )
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()

        if self.request.method == "POST":
            context["patient"] = self.get_patient_profile()

        return context

    def perform_update(self, serializer):
        symptom_case = self.get_object()
        patient = self.get_patient_profile()

        if symptom_case.patient_id != patient.patient_id:
            raise PermissionDenied(
                "본인의 증상 기록만 수정할 수 있습니다."
            )

        serializer.save()

    def perform_destroy(self, instance):
        patient = self.get_patient_profile()

        if instance.patient_id != patient.patient_id:
            raise PermissionDenied(
                "본인의 증상 기록만 삭제할 수 있습니다."
            )

        instance.delete()


class PatientSymptomImageViewSet(viewsets.ModelViewSet):
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
        symptom_image = self.get_object()
        patient = self.get_patient_profile()

        if (
            symptom_image.symptom_case.patient_id
            != patient.patient_id
        ):
            raise PermissionDenied(
                "본인의 증상 사진만 수정할 수 있습니다."
            )

        serializer.save(
            symptom_case=symptom_image.symptom_case,
        )

    def perform_destroy(self, instance):
        patient = self.get_patient_profile()

        if (
            instance.symptom_case.patient_id
            != patient.patient_id
        ):
            raise PermissionDenied(
                "본인의 증상 사진만 삭제할 수 있습니다."
            )

        instance.delete()