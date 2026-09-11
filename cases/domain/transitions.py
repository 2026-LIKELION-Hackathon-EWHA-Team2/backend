from selfsymptoms.models import PatientSymptomCase

from ..exceptions import InvalidStateTransitionError
from ..models import (
    CaseAgreement,
    CaseCollaborationRequest,
    CaseTransfer,
    MedicalCase,
)


TRANSFER_STATUS_TRANSITIONS = {
    CaseTransfer.Status.REVIEW_REQUIRED: {
        CaseTransfer.Status.READY_TO_TRANSFER,
    },
    CaseTransfer.Status.READY_TO_TRANSFER: {
        CaseTransfer.Status.TRANSFERRED,
    },
}

COLLABORATION_STATUS_TRANSITIONS = {
    CaseCollaborationRequest.Status.REQUESTED: {
        CaseCollaborationRequest.Status.ACCEPTED,
    },
    CaseCollaborationRequest.Status.ACCEPTED: {
        CaseCollaborationRequest.Status.COMPLETED,
    },
}

AGREEMENT_STATUS_TRANSITIONS = {
    CaseAgreement.Status.AI_DRAFT: {
        CaseAgreement.Status.IN_REVIEW,
        CaseAgreement.Status.FINAL,
    },
    CaseAgreement.Status.IN_REVIEW: {
        CaseAgreement.Status.IN_REVIEW,
        CaseAgreement.Status.FINAL,
    },
}

SYMPTOM_CASE_STATUS_TRANSITIONS = {
    PatientSymptomCase.Status.HOSPITAL_SELECTED: {
        PatientSymptomCase.Status.CONNECTION_REQUESTED,
    },
    PatientSymptomCase.Status.CONNECTION_REQUESTED: {
        PatientSymptomCase.Status.IN_COLLABORATION,
    },
    PatientSymptomCase.Status.IN_COLLABORATION: {
        PatientSymptomCase.Status.COMPLETED,
    },
}


def _ensure_transition(*, current, target, transitions, detail):
    if target not in transitions.get(current, set()):
        raise InvalidStateTransitionError(detail)


def ensure_transfer_reviewable(transfer, agreements):
    _ensure_transition(
        current=transfer.status,
        target=CaseTransfer.Status.READY_TO_TRANSFER,
        transitions=TRANSFER_STATUS_TRANSITIONS,
        detail="번역·구조화 완료 후 입력할 수 있습니다.",
    )
    if not all(agreements):
        raise InvalidStateTransitionError("필수 동의가 필요합니다.")


def ensure_transfer_sendable(transfer):
    _ensure_transition(
        current=transfer.status,
        target=CaseTransfer.Status.TRANSFERRED,
        transitions=TRANSFER_STATUS_TRANSITIONS,
        detail={"detail": "전송 준비가 완료되지 않았습니다."},
    )
    if not all(
        (
            transfer.procedure_medication_agreed,
            transfer.adverse_effect_clinician_note_agreed,
            transfer.overseas_ai_processing_agreed,
        )
    ):
        raise InvalidStateTransitionError(
            {"detail": "필수 동의가 완료되지 않았습니다."}
        )
    if not any(
        (
            transfer.include_patient_info,
            transfer.include_procedure_info,
            transfer.include_adverse_effects,
            transfer.include_clinician_note,
        )
    ):
        raise InvalidStateTransitionError(
            {"detail": "전송 항목을 하나 이상 선택해야 합니다."}
        )


def ensure_collaboration_acceptable(collaboration_request):
    _ensure_transition(
        current=collaboration_request.status,
        target=CaseCollaborationRequest.Status.ACCEPTED,
        transitions=COLLABORATION_STATUS_TRANSITIONS,
        detail={"detail": "현재 상태에서는 협진 요청을 수락할 수 없습니다."},
    )


def ensure_collaboration_case_transferred(collaboration_request):
    if collaboration_request.medical_case.status != MedicalCase.Status.TRANSFERRED:
        raise InvalidStateTransitionError(
            {
                "detail": (
                    "환자의 의료정보 전송 동의가 "
                    "완료되지 않은 케이스입니다."
                )
            }
        )


def ensure_agreement_editable(agreement):
    _ensure_transition(
        current=agreement.status,
        target=CaseAgreement.Status.IN_REVIEW,
        transitions=AGREEMENT_STATUS_TRANSITIONS,
        detail={"detail": "최종 합의가 완료된 후에는 수정할 수 없습니다."},
    )


def ensure_agreement_reviewable(agreement):
    _ensure_transition(
        current=agreement.status,
        target=CaseAgreement.Status.FINAL,
        transitions=AGREEMENT_STATUS_TRANSITIONS,
        detail="이미 최종 합의가 완료되었습니다.",
    )
