import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from ..models import (
    CaseChatMessage,
    CaseChatMessageTranslation,
    CaseChatReadState,
    CaseChatRoom,
)
from .ai import translate_medical_message

logger = logging.getLogger(__name__)


def create_chat_message(*, chat_room, sender, validated_data):
    source_language = sender.preferred_language
    message = CaseChatMessage.objects.create(
        chat_room=chat_room,
        sender=sender,
        source_language=source_language,
        **validated_data,
    )

    if sender.id == chat_room.medical_case.origin_hospital_id:
        recipient = chat_room.partner_hospital
    else:
        recipient = chat_room.medical_case.origin_hospital

    target_language = recipient.preferred_language
    if source_language != target_language:
        translation = CaseChatMessageTranslation.objects.create(
            message=message,
            target_language=target_language,
            model_name=settings.OPENAI_TRANSLATION_MODEL,
            status=CaseChatMessageTranslation.Status.PENDING,
        )
        try:
            translation.translated_content = translate_medical_message(
                text=message.content,
                source_language=source_language,
                target_language=target_language,
            )
            translation.status = CaseChatMessageTranslation.Status.COMPLETED
            translation.save(
                update_fields=(
                    "translated_content",
                    "status",
                    "updated_at",
                )
            )
        except Exception as exc:
            logger.exception("OpenAI message translation failed")
            translation.status = CaseChatMessageTranslation.Status.FAILED
            translation.error_code = exc.__class__.__name__
            translation.save(
                update_fields=(
                    "status",
                    "error_code",
                    "updated_at",
                )
            )

    return (
        CaseChatMessage.objects
        .select_related("sender")
        .prefetch_related("translations")
        .get(id=message.id)
    )


@transaction.atomic
def mark_chat_room_read(*, room_id, hospital, last_read_message_id=None):
    chat_room = get_object_or_404(
        CaseChatRoom.objects.select_related(
            "medical_case",
            "medical_case__origin_hospital",
            "partner_hospital",
        ),
        id=room_id,
        is_active=True,
    )

    if hospital.id not in {
        chat_room.medical_case.origin_hospital_id,
        chat_room.partner_hospital_id,
    }:
        raise PermissionDenied(
            "해당 협진 채팅방에 접근할 권한이 없습니다."
        )

    if last_read_message_id is None:
        target_message = chat_room.messages.order_by("-id").first()
    else:
        target_message = get_object_or_404(
            chat_room.messages,
            id=last_read_message_id,
        )

    read_state, _ = (
        CaseChatReadState.objects
        .select_for_update()
        .get_or_create(
            chat_room=chat_room,
            hospital=hospital,
        )
    )

    if (
        target_message is not None
        and (
            read_state.last_read_message_id is None
            or target_message.id > read_state.last_read_message_id
        )
    ):
        read_state.last_read_message = target_message
        read_state.save(
            update_fields=["last_read_message", "updated_at"]
        )

    remaining_unread = chat_room.messages.exclude(sender=hospital)
    if read_state.last_read_message_id is not None:
        remaining_unread = remaining_unread.filter(
            id__gt=read_state.last_read_message_id,
        )

    return chat_room, read_state, remaining_unread.count()
