from django.db.models import Count, Q

from cases.models import MedicalCase


COLLABORATION_COUNT_ATTRIBUTE = "completed_collaboration_count"


def with_collaboration_count(queryset):
    """Annotate hospitals with their completed transfer count."""
    return queryset.annotate(
        completed_collaboration_count=Count(
            "user__received_cases",
            filter=Q(
                user__received_cases__status=MedicalCase.Status.TRANSFERRED,
            ),
        )
    )
