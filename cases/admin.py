from django.contrib import admin

from .models import (
    CaseAgreement,
    CaseCollaborationRequest,
    CaseTransfer,
)


@admin.register(CaseTransfer)
class CaseTransferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "medical_case",
        "symptom_case",
        "patient",
        "partner_hospital",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "include_patient_info",
        "include_procedure_info",
        "include_adverse_effects",
        "include_clinician_note",
    )
    search_fields = (
        "patient__name",
        "partner_hospital__name",
        "medical_case__id",
        "symptom_case__symptom_case_id",
    )
    readonly_fields = (
        "structured_data",
        "translated_data",
        "created_at",
        "updated_at",
    )


@admin.register(CaseCollaborationRequest)
class CaseCollaborationRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "medical_case",
        "status",
        "requested_at",
        "accepted_at",
        "completed_at",
    )
    list_filter = (
        "status",
        "requested_at",
    )
    search_fields = (
        "medical_case__patient__name",
        "medical_case__origin_hospital__name",
        "medical_case__partner_hospital__name",
    )
    readonly_fields = (
        "requested_at",
        "created_at",
        "updated_at",
    )

@admin.register(CaseAgreement)
class CaseAgreementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "chat_room",
        "status",
        "version",
        "edited_by",
        "finalized_at",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
        "finalized_at",
    )

    search_fields = (
        "chat_room__medical_case__patient__name",
        "chat_room__medical_case__origin_hospital__name",
        "chat_room__partner_hospital__name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "합의안 정보",
            {
                "fields": (
                    "chat_room",
                    "status",
                    "version",
                )
            },
        ),
        (
            "한국어 원본",
            {
                "fields": (
                    "judgment_draft",
                    "evidence_items",
                    "additional_opinion",
                )
            },
        ),
        (
            "언어별 합의안",
            {
                "fields": (
                    "localized_content",
                )
            },
        ),
        (
            "편집 및 완료 정보",
            {
                "fields": (
                    "edited_by",
                    "edited_at",
                    "finalized_at",
                    "revision_requested_by",
                    "revision_requested_at",
                )
            },
        ),
        (
            "관리 정보",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )