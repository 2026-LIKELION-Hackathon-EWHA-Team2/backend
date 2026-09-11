import re

from django.db.models import Q

from ..models import CaseCollaborationRequest


def get_collaboration_requests_for_participating_hospital(user):
    """Return requests where the hospital participates on either side."""
    return (
        CaseCollaborationRequest.objects
        .filter(
            Q(medical_case__origin_hospital=user)
            | Q(medical_case__partner_hospital=user)
        )
        .select_related(
            "medical_case",
            "medical_case__patient",
            "medical_case__origin_hospital",
            "medical_case__partner_hospital",
        )
        .prefetch_related(
            "medical_case__ingredients",
            "medical_case__chat_rooms",
            "medical_case__case_transfers",
            "medical_case__case_transfers__symptom_case__images",
        )
        .order_by("-requested_at")
    )


def get_received_collaboration_requests_for_user(user):
    return (
        CaseCollaborationRequest.objects
        .filter(medical_case__partner_hospital=user)
        .select_related(
            "medical_case",
            "medical_case__patient",
            "medical_case__origin_hospital",
            "medical_case__partner_hospital",
        )
        .prefetch_related(
            "medical_case__ingredients",
            "medical_case__chat_rooms",
            "medical_case__case_transfers",
            "medical_case__case_transfers__symptom_case__images",
        )
        .order_by("-requested_at")
    )


def filter_collaboration_requests(queryset, *, status_value=None, search=""):
    if status_value is not None:
        queryset = queryset.filter(status=status_value)

    search = search.strip()
    if not search:
        return queryset

    search_filter = Q(
        medical_case__patient__name__icontains=search,
    )
    case_id_match = re.search(r"(\d+)$", search)
    if case_id_match is not None:
        search_filter |= Q(
            medical_case_id=int(case_id_match.group(1)),
        )

    return queryset.filter(search_filter)
