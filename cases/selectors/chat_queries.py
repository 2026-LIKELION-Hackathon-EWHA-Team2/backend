from django.db.models import F, Max, OuterRef, Prefetch, Q, Subquery

from ..models import (
    CaseChatMessage,
    CaseChatReadState,
    CaseChatRoom,
)


def get_total_unread_count_for_hospital(user):
    last_read_message_id = (
        CaseChatReadState.objects
        .filter(
            chat_room_id=OuterRef("chat_room_id"),
            hospital=user,
        )
        .values("last_read_message_id")[:1]
    )

    return (
        CaseChatMessage.objects
        .filter(
            Q(chat_room__medical_case__origin_hospital=user)
            | Q(chat_room__partner_hospital=user),
            chat_room__is_active=True,
        )
        .exclude(sender=user)
        .annotate(
            viewer_last_read_message_id=Subquery(
                last_read_message_id
            )
        )
        .filter(
            Q(viewer_last_read_message_id__isnull=True)
            | Q(id__gt=F("viewer_last_read_message_id"))
        )
        .count()
    )


def get_chat_room_queryset():
    return CaseChatRoom.objects.select_related(
        "medical_case",
        "medical_case__origin_hospital",
        "partner_hospital",
    )


def get_chat_messages(chat_room):
    return (
        chat_room.messages
        .select_related("sender")
        .prefetch_related("translations")
        .order_by("id")
    )


def get_chat_rooms_for_hospital(user):
    return (
        CaseChatRoom.objects
        .filter(
            Q(medical_case__origin_hospital=user)
            | Q(partner_hospital=user),
            is_active=True,
        )
        .select_related(
            "medical_case",
            "medical_case__patient",
            "medical_case__origin_hospital",
            "medical_case__partner_hospital",
            "medical_case__collaboration_request",
            "partner_hospital",
            "agreement",
        )
        .prefetch_related(
            Prefetch(
                "messages",
                queryset=(
                    CaseChatMessage.objects
                    .select_related("sender")
                    .prefetch_related("translations")
                    .order_by("id")
                ),
                to_attr="chat_list_messages",
            ),
            Prefetch(
                "read_states",
                queryset=CaseChatReadState.objects.filter(
                    hospital=user,
                ),
                to_attr="viewer_read_states",
            ),
        )
        .annotate(latest_message_at=Max("messages__created_at"))
        .order_by("-latest_message_at", "-created_at")
        .distinct()
    )
