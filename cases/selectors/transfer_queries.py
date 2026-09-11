from django.db.models import F, Max, Prefetch, Q

from accounts.models import User
from selfsymptoms.models import PatientSymptomCase

from ..models import (
    CaseAgreement,
    CaseAgreementReview,
    CaseChatRoom,
    CaseTransfer,
    MedicalCase,
)


def get_medical_cases_for_user(user):
    if user.user_type == User.UserType.PATIENT:
        return MedicalCase.objects.filter(patient=user)

    if user.user_type == User.UserType.HOSPITAL:
        return MedicalCase.objects.filter(
            Q(origin_hospital=user)
            | Q(
                partner_hospital=user,
                status=MedicalCase.Status.TRANSFERRED,
            )
        ).distinct()

    return MedicalCase.objects.none()


def get_medical_case_detail_queryset():
    return MedicalCase.objects.select_related(
        "patient",
        "origin_hospital",
        "partner_hospital",
    ).prefetch_related("ingredients")


def get_patient_procedure_history_list(user):
    return (
        MedicalCase.objects
        .filter(
            patient=user,
            case_transfers__symptom_case__status=(
                PatientSymptomCase.Status.COMPLETED
            ),
        )
        .select_related(
            "origin_hospital",
            "origin_hospital__hospital_profile",
        )
        .prefetch_related(
            Prefetch(
                "case_transfers",
                queryset=(
                    CaseTransfer.objects
                    .filter(
                        symptom_case__status=(
                            PatientSymptomCase.Status.COMPLETED
                        )
                    )
                    .select_related("symptom_case")
                ),
                to_attr="completed_case_transfers",
            )
        )
        .annotate(
            finalized_at=Max(
                "chat_rooms__agreement__finalized_at",
                filter=Q(
                    chat_rooms__agreement__status=(
                        CaseAgreement.Status.FINAL
                    )
                ),
            )
        )
        .order_by(
            F("finalized_at").desc(nulls_last=True),
            "-id",
        )
        .distinct()
    )


def get_patient_procedure_history_detail(user):
    final_chat_rooms = (
        CaseChatRoom.objects
        .filter(
            agreement__status=CaseAgreement.Status.FINAL,
            agreement__finalized_at__isnull=False,
        )
        .select_related(
            "partner_hospital",
            "agreement",
        )
        .prefetch_related(
            Prefetch(
                "agreement__reviews",
                queryset=(
                    CaseAgreementReview.objects
                    .select_related("hospital")
                    .order_by("reviewed_at", "id")
                ),
            )
        )
        .order_by("-agreement__finalized_at", "-id")
    )

    return (
        MedicalCase.objects
        .filter(
            patient=user,
            case_transfers__symptom_case__status=(
                PatientSymptomCase.Status.COMPLETED
            ),
            chat_rooms__agreement__status=CaseAgreement.Status.FINAL,
            chat_rooms__agreement__finalized_at__isnull=False,
        )
        .select_related(
            "origin_hospital",
            "origin_hospital__hospital_profile",
            "partner_hospital",
        )
        .prefetch_related(
            Prefetch(
                "case_transfers",
                queryset=(
                    CaseTransfer.objects
                    .filter(
                        symptom_case__status=(
                            PatientSymptomCase.Status.COMPLETED
                        )
                    )
                    .select_related("symptom_case")
                    .order_by("id")
                ),
                to_attr="completed_case_transfers",
            ),
            Prefetch(
                "chat_rooms",
                queryset=final_chat_rooms,
                to_attr="final_agreement_chat_rooms",
            ),
        )
        .distinct()
    )


def get_patient_transfer_queryset(user):
    return CaseTransfer.objects.filter(
        patient=user,
        status__in=(
            CaseTransfer.Status.REVIEW_REQUIRED,
            CaseTransfer.Status.READY_TO_TRANSFER,
        ),
    ).select_related(
        "recommendation",
        "partner_hospital",
        "medical_case",
        "medical_case__origin_hospital",
    )


def get_patient_transfer_list(user):
    return get_patient_transfer_queryset(user).order_by("-created_at")


def get_patient_transfers_for_review(user):
    return CaseTransfer.objects.filter(patient=user)


def get_partner_transfer_queryset(user):
    if user.user_type != User.UserType.HOSPITAL:
        return CaseTransfer.objects.none()

    return (
        CaseTransfer.objects
        .filter(
            partner_hospital=user,
            status=CaseTransfer.Status.TRANSFERRED,
        )
        .select_related(
            "partner_hospital",
            "medical_case",
            "medical_case__origin_hospital",
            "medical_case__collaboration_request",
        )
    )


def get_partner_transfer_list(user):
    return get_partner_transfer_queryset(user).order_by("-transferred_at")
