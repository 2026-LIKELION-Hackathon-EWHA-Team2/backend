import logging
from datetime import date

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from selfsymptoms.models import DiagnosisAnalysis

from ..models import (
    CaseIngredient,
    CaseCollaborationRequest,
    CaseTransfer,
    MedicalCase,
)
from ..permissions import IsPatient
from ..selectors.transfer_queries import (
    get_medical_case_detail_queryset,
    get_medical_cases_for_user,
    get_partner_transfer_list,
    get_partner_transfer_queryset,
    get_patient_procedure_history_detail,
    get_patient_procedure_history_list,
    get_patient_transfer_list,
    get_patient_transfer_queryset,
    get_patient_transfers_for_review,
)
from ..services import (
    analyze_diagnosis_document,
    generate_patient_symptom_translation_summary,
)
from ..serializers import (
    CaseTransferCreateSerializer,
    CaseTransferDetailSerializer,
    CaseTransferListSerializer,
    CaseTransferReviewSerializer,
    MedicalCaseDetailSerializer,
    PartnerCaseTransferSerializer,
    PatientProcedureHistoryDetailSerializer,
    PatientProcedureHistoryListSerializer,
)

logger = logging.getLogger(__name__)


class MedicalCaseListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MedicalCaseDetailSerializer

    def get_queryset(self):
        return get_medical_cases_for_user(self.request.user)

class MedicalCaseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id):
        medical_case = get_object_or_404(
            get_medical_case_detail_queryset(),
            id=case_id,
        )

        is_patient = (
            medical_case.patient_id
            == request.user.id
        )
        is_origin = (
            medical_case.origin_hospital_id
            == request.user.id
        )
        is_partner = (
            medical_case.partner_hospital_id
            == request.user.id
            and medical_case.status
            == MedicalCase.Status.TRANSFERRED
        )

        if not (
            is_patient
            or is_origin
            or is_partner
        ):
            raise PermissionDenied(
                "해당 케이스를 조회할 권한이 없습니다."
            )

        return Response(
            MedicalCaseDetailSerializer(
                medical_case
            ).data
        )


class PatientProcedureHistoryListView(generics.ListAPIView):
    permission_classes = [IsPatient]
    serializer_class = PatientProcedureHistoryListSerializer

    def get_queryset(self):
        return get_patient_procedure_history_list(
            self.request.user
        )


class PatientProcedureHistoryDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPatient]
    serializer_class = PatientProcedureHistoryDetailSerializer
    lookup_url_kwarg = "medical_case_id"

    def get_queryset(self):
        return get_patient_procedure_history_detail(
            self.request.user
        )



class CaseTransferListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsPatient()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CaseTransferListSerializer
        return CaseTransferCreateSerializer

    def get_queryset(self):
        return get_patient_transfer_list(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        symptom_case = serializer.validated_data["symptom_case"]
        recommendation = serializer.validated_data["recommendation"]
        partner_hospital = recommendation.hospital.user

        symptom_data = {
            "description": symptom_case.description,
            "start_date": (
                symptom_case.symptom_start_date.isoformat()
                if symptom_case.symptom_start_date
                else None
            ),
            "onset_timing": symptom_case.get_onset_timing_display()
            if symptom_case.onset_timing
            else None,
            "pain_level": symptom_case.pain_level,
            "areas": [
                area.get_area_type_display()
                for area in symptom_case.areas.all()
            ],
            "types": [
                symptom_type.custom_symptom
                or symptom_type.get_symptom_type_display()
                for symptom_type in symptom_case.symptom_types.all()
            ],
        }

        partner_language = (
            partner_hospital.preferred_language
        )

        origin_language = (
            symptom_case.diagnosed_hospital.user.preferred_language
        )

        try:
            document_result = analyze_diagnosis_document(
                symptom_case.diagnosis_document,
                partner_language,
                symptom_data,
            )
        except Exception as exc:
            logger.exception("Diagnosis document analysis failed")
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )


        procedure = document_result["procedure"]
        try:
            procedure_date = date.fromisoformat(procedure["date"])
        except (TypeError, ValueError):
            return Response(
                {
                    "detail": (
                        "진단서에서 추출한 시술일 형식이 "
                        "올바르지 않습니다."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            ai_summary = generate_patient_symptom_translation_summary(
                symptom_data,
                partner_language,
            )
        except Exception as exc:
            logger.exception("Case translation summary generation failed")
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        origin_document_result = document_result
        origin_ai_summary = ai_summary

        if origin_language != partner_language:
            try:
                origin_document_result = analyze_diagnosis_document(
                    symptom_case.diagnosis_document,
                    origin_language,
                    symptom_data,
                )
                origin_ai_summary = (
                    generate_patient_symptom_translation_summary(
                        symptom_data,
                        origin_language,
                    )
                )
            except Exception as exc:
                logger.exception(
                    "Origin hospital translation generation failed"
                )
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        translated_symptoms = document_result.get("symptoms") or {}
        patient_birth_date = serializer.validated_data.get(
            "patient_birth_date"
        )
        structured_data = {
            "patient_info": {
                "name": serializer.validated_data["patient_name"],
                "gender": serializer.validated_data.get(
                    "patient_gender"
                ),
                "birth_date": (
                     patient_birth_date.isoformat()
                     if patient_birth_date
                     else None
                ),
            },
            "symptoms": {
                "description": (
                    translated_symptoms.get("description")
                    or symptom_data["description"]
                ),
                "start_date": (
                    translated_symptoms.get("start_date")
                    or symptom_data["start_date"]
                ),
                "onset_timing": (
                    translated_symptoms.get("onset_timing")
                    or symptom_data["onset_timing"]
                ),
                "pain_level": (
                    translated_symptoms.get("pain_level")
                    if translated_symptoms.get("pain_level") is not None
                    else symptom_data["pain_level"]
                ),
                "areas": (
                    translated_symptoms.get("areas")
                    or symptom_data["areas"]
                ),
                "types": (
                    translated_symptoms.get("types")
                    or symptom_data["types"]
                ),
                "images": list(
                    symptom_case.images.values_list(
                        "image",
                        flat=True,
                    )
                ),
            },
            "procedure": procedure,
            "ingredients": document_result["ingredients"],
            "clinician_note": document_result["clinician_note"],
            "ai_summary": ai_summary,
        }

        origin_translated_symptoms = (
            origin_document_result.get("symptoms") or {}
        )
        origin_structured_data = {
            "patient_info": structured_data["patient_info"],
            "symptoms": {
                "description": (
                    origin_translated_symptoms.get("description")
                    or symptom_data["description"]
                ),
                "start_date": (
                    origin_translated_symptoms.get("start_date")
                    or symptom_data["start_date"]
                ),
                "onset_timing": (
                    origin_translated_symptoms.get("onset_timing")
                    or symptom_data["onset_timing"]
                ),
                "pain_level": (
                    origin_translated_symptoms.get("pain_level")
                    if origin_translated_symptoms.get("pain_level")
                    is not None
                    else symptom_data["pain_level"]
                ),
                "areas": (
                    origin_translated_symptoms.get("areas")
                    or symptom_data["areas"]
                ),
                "types": (
                    origin_translated_symptoms.get("types")
                    or symptom_data["types"]
                ),
                "images": structured_data["symptoms"]["images"],
            },
            "procedure": origin_document_result["procedure"],
            "ingredients": origin_document_result["ingredients"],
            "clinician_note": origin_document_result["clinician_note"],
            "ai_summary": origin_ai_summary,
        }

        with transaction.atomic():
            DiagnosisAnalysis.objects.update_or_create(
                symptom_case=symptom_case,
                defaults={
                    "extracted_text": document_result[
                        "extracted_text"
                    ],
                    "analysis_result": {
                        key: value
                        for key, value in document_result.items()
                        if key != "extracted_text"
                    },
                    "analyzed_at": timezone.now(),
                },
            )

            medical_case = MedicalCase.objects.create(
                patient=request.user,
                origin_hospital=(
                    symptom_case.diagnosed_hospital.user
                ),
                partner_hospital=partner_hospital,
                procedure_name=procedure["name"],
                procedure_area=procedure["area"],
                procedure_date=procedure_date,
                clinician_note=document_result["clinician_note"],
                ai_summary=ai_summary,
                status=MedicalCase.Status.READY_TO_TRANSFER,
            )

            CaseIngredient.objects.bulk_create(
                [
                    CaseIngredient(
                        medical_case=medical_case,
                        ingredient_name=ingredient,
                    )
                    for ingredient
                    in dict.fromkeys(document_result["ingredients"])
                ]
            )

            transfer = serializer.save(
                medical_case=medical_case,
                structured_data=structured_data,
                translated_data={
                    partner_language: structured_data,
                    origin_language: origin_structured_data,
                },
                status=CaseTransfer.Status.REVIEW_REQUIRED,
                processing_error="",
            )

        return Response(
            CaseTransferDetailSerializer(transfer).data,
            status=status.HTTP_201_CREATED,
        )


class CaseTransferDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPatient]
    serializer_class = CaseTransferDetailSerializer
    lookup_url_kwarg = "transfer_id"

    def get_queryset(self):
        return get_patient_transfer_queryset(self.request.user)


class CaseTransferReviewView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CaseTransferReviewSerializer
    lookup_url_kwarg = "transfer_id"
    http_method_names = ["patch"]

    def get_queryset(self):
        return get_patient_transfers_for_review(self.request.user)

    def patch(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(
            transfer,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        transfer = serializer.save()

        return Response(
            CaseTransferDetailSerializer(transfer).data,
            status=status.HTTP_200_OK,
        )


class CaseTransferSendView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, transfer_id):
        transfer = get_object_or_404(
            CaseTransfer.objects.select_for_update(),
            id=transfer_id,
            patient=request.user,
        )

        if transfer.status != CaseTransfer.Status.READY_TO_TRANSFER:
            return Response(
                {"detail": "전송 준비가 완료되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not all([
            transfer.procedure_medication_agreed,
            transfer.adverse_effect_clinician_note_agreed,
            transfer.overseas_ai_processing_agreed,
        ]):
            return Response(
                {"detail": "필수 동의가 완료되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not any([
            transfer.include_patient_info,
            transfer.include_procedure_info,
            transfer.include_adverse_effects,
            transfer.include_clinician_note,
        ]):
            return Response(
                {"detail": "전송 항목을 하나 이상 선택해야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transfer.status = CaseTransfer.Status.TRANSFERRED
        transfer.transferred_at = timezone.now()
        transfer.save(
            update_fields=[
                "status",
                "transferred_at",
                "updated_at",
            ]
        )

        medical_case = transfer.medical_case
        medical_case.partner_hospital = transfer.partner_hospital
        medical_case.status = MedicalCase.Status.TRANSFERRED
        medical_case.transferred_at = transfer.transferred_at
        medical_case.save(
            update_fields=[
                "partner_hospital",
                "status",
                "transferred_at",
                "updated_at",
            ]
        )

        CaseCollaborationRequest.objects.get_or_create(
            medical_case=medical_case,
            defaults={
                "status": CaseCollaborationRequest.Status.REQUESTED,
            },
        )

        symptom_case = transfer.symptom_case
        symptom_case.status = symptom_case.Status.CONNECTION_REQUESTED
        symptom_case.save(
            update_fields=["status", "updated_at"]
        )

        return Response(
            CaseTransferDetailSerializer(transfer).data,
            status=status.HTTP_200_OK,
        )


class PartnerCaseTransferListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartnerCaseTransferSerializer

    def get_queryset(self):
        return get_partner_transfer_list(self.request.user)


class PartnerCaseTransferDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartnerCaseTransferSerializer
    lookup_url_kwarg = "transfer_id"

    def get_queryset(self):
        return get_partner_transfer_queryset(self.request.user)
