from ..models import CaseAgreement, CaseChatRoom


def get_agreement_chat_room_queryset():
    return CaseChatRoom.objects.select_related(
        "medical_case",
        "medical_case__origin_hospital",
        "partner_hospital",
    )


def get_agreement_detail_queryset():
    return (
        CaseAgreement.objects
        .select_related("edited_by", "chat_room")
        .prefetch_related(
            "reviews__hospital",
            "revisions",
        )
    )


def get_agreement_revisions(agreement):
    return (
        agreement.revisions
        .select_related("edited_by")
        .order_by("-version")
    )
