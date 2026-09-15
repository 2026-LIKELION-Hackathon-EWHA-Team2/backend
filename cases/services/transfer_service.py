import hashlib
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from selfsymptoms.models import DiagnosisAnalysis

from ..domain.transitions import (
    ensure_transfer_reviewable,
    ensure_transfer_sendable,
)
from ..models import (
    CaseCollaborationRequest,
    CaseIngredient,
    CaseTransfer,
    MedicalCase,
)


def _calculate_analysis_input_checksum(document, symptom_data):
    digest = hashlib.sha256()
    document.open("rb")
    try:
        while chunk := document.read(64 * 1024):
            digest.update(chunk)
    finally:
        document.close()
    digest.update(b"\0")
    digest.update(
        json.dumps(
            symptom_data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return digest.hexdigest()


def get_or_analyze_diagnosis_document(
    *,
    symptom_case,
    target_language,
    symptom_data,
    analyzer,
):
    checksum = _calculate_analysis_input_checksum(
        symptom_case.diagnosis_document,
        symptom_data,
    )
    cached = DiagnosisAnalysis.objects.filter(
        symptom_case=symptom_case,
        analysis_input_checksum=checksum,
        analysis_language=target_language,
    ).first()

    if cached and isinstance(cached.analysis_result, dict):
        required_fields = {
            "symptoms",
            "procedure",
            "ingredients",
            "clinician_note",
        }
        if required_fields.issubset(cached.analysis_result):
            return {
                "extracted_text": cached.extracted_text or "",
                **cached.analysis_result,
            }

    result = analyzer(
        symptom_case.diagnosis_document,
        target_language,
        symptom_data,
    )
    DiagnosisAnalysis.objects.update_or_create(
        symptom_case=symptom_case,
        defaults={
            "extracted_text": result["extracted_text"],
            "analysis_result": {
                key: value
                for key, value in result.items()
                if key != "extracted_text"
            },
            "analysis_language": target_language,
            "analysis_input_checksum": checksum,
            "analyzed_at": timezone.now(),
        },
    )
    return result


@transaction.atomic
def create_case_transfer_records(
    *,
    serializer,
    patient,
    symptom_case,
    partner_hospital,
    procedure_date,
    document_result,
    ai_summary,
    structured_data,
    origin_structured_data,
    partner_language,
    origin_language,
):
    medical_case = MedicalCase.objects.create(
        patient=patient,
        origin_hospital=symptom_case.diagnosed_hospital.user,
        partner_hospital=partner_hospital,
        procedure_name=document_result["procedure"]["name"],
        procedure_area=document_result["procedure"]["area"],
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
            for ingredient in dict.fromkeys(document_result["ingredients"])
        ]
    )

    return serializer.save(
        medical_case=medical_case,
        structured_data=structured_data,
        translated_data={
            partner_language: structured_data,
            origin_language: origin_structured_data,
        },
        status=CaseTransfer.Status.REVIEW_REQUIRED,
        processing_error="",
    )


def review_case_transfer(transfer, validated_data):
    ensure_transfer_reviewable(
        transfer,
        (
            validated_data.get("procedure_medication_agreed", False),
            validated_data.get(
                "adverse_effect_clinician_note_agreed",
                False,
            ),
            validated_data.get("overseas_ai_processing_agreed", False),
        ),
    )
    for field, value in validated_data.items():
        setattr(transfer, field, value)

    structured_data = transfer.structured_data or {}
    adverse_effects = list(
        transfer.symptom_case.symptom_types.values_list(
            "symptom_type",
            flat=True,
        )
    )

    transfer.adverse_effects = list(dict.fromkeys(adverse_effects))
    transfer.include_patient_info = bool(
        structured_data.get("patient_info")
    )
    transfer.include_procedure_info = bool(
        structured_data.get("procedure")
        or structured_data.get("ingredients")
    )
    transfer.include_adverse_effects = bool(transfer.adverse_effects)
    transfer.include_clinician_note = bool(
        structured_data.get("clinician_note")
    )
    transfer.agreed_at = timezone.now()
    transfer.status = CaseTransfer.Status.READY_TO_TRANSFER
    transfer.save()
    return transfer


@transaction.atomic
def send_case_transfer(*, transfer_id, patient):
    transfer = get_object_or_404(
        CaseTransfer.objects.select_for_update(),
        id=transfer_id,
        patient=patient,
    )

    ensure_transfer_sendable(transfer)

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
    symptom_case.save(update_fields=["status", "updated_at"])
    return transfer
