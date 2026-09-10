import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F, Max, OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    CaseAgreement,
    CaseChatMessage,
    CaseChatMessageTranslation,
    CaseChatReadState,
    CaseChatRoom,
)
from ..permissions import IsCaseChatParticipant, IsHospital
from ..services import translate_medical_message
from ..serializers import (
    CaseChatMessageSerializer,
    CaseChatRoomListSerializer,
)

logger = logging.getLogger(__name__)


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

class CaseChatMessageListCreateView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsCaseChatParticipant,
    ]

    def get_chat_room(self, request, case_id, room_id):
        chat_room = get_object_or_404(
            CaseChatRoom.objects.select_related(
                "medical_case",
                "medical_case__origin_hospital",
                "partner_hospital",
            ),
            id=room_id,
            medical_case_id=case_id,
        )

        self.check_object_permissions(
            request,
            chat_room,
        )

        return chat_room

    def get(self, request, case_id, room_id):
        chat_room = self.get_chat_room(
            request,
            case_id,
            room_id,
        )

        messages = (
            chat_room.messages
            .select_related("sender")
            .prefetch_related("translations")
            .order_by("id")
        )

        return Response(
            {
                "messages": CaseChatMessageSerializer(
                    messages,
                    many=True,
                    context={"request": request},
                ).data
            }
        )

    def post(self, request, case_id, room_id):
        chat_room = self.get_chat_room(
            request,
            case_id,
            room_id,
        )

        serializer = CaseChatMessageSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        source_language = (
            request.user.preferred_language
        )

        message = serializer.save(
            chat_room=chat_room,
            sender=request.user,
            source_language=source_language,
        )

        if (
            request.user.id
            == chat_room.medical_case.origin_hospital_id
        ):
            recipient = chat_room.partner_hospital
        else:
            recipient = (
                chat_room.medical_case.origin_hospital
            )

        target_language = (
            recipient.preferred_language
        )

        if source_language != target_language:
            translation = (
                CaseChatMessageTranslation.objects.create(
                    message=message,
                    target_language=target_language,
                    model_name=(
                        settings.OPENAI_TRANSLATION_MODEL
                    ),
                    status=(
                        CaseChatMessageTranslation
                        .Status
                        .PENDING
                    ),
                )
            )

            try:
                translated_content = (
                    translate_medical_message(
                        text=message.content,
                        source_language=source_language,
                        target_language=target_language,
                    )
                )

                translation.translated_content = (
                    translated_content
                )
                translation.status = (
                    CaseChatMessageTranslation
                    .Status
                    .COMPLETED
                )
                translation.save(
                    update_fields=(
                        "translated_content",
                        "status",
                        "updated_at",
                    )
                )

            except Exception as exc:
                logger.exception(
                    "OpenAI message translation failed"
                )

                translation.status = (
                    CaseChatMessageTranslation
                    .Status
                    .FAILED
                )
                translation.error_code = (
                    exc.__class__.__name__
                )
                translation.save(
                    update_fields=(
                        "status",
                        "error_code",
                        "updated_at",
                    )
                )

        message = (
            message.__class__.objects
            .select_related("sender")
            .prefetch_related("translations")
            .get(id=message.id)            
        
        )

        return Response(
            CaseChatMessageSerializer(
                message,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )



class CaseChatRoomListView(generics.ListAPIView):
    permission_classes = [IsHospital]
    serializer_class = CaseChatRoomListSerializer

    def get_queryset(self):
        user = self.request.user
        chat_status = self.request.query_params.get("status")
        valid_statuses = {
            CaseChatRoomListSerializer.ChatStatus.IN_REVIEW,
            CaseChatRoomListSerializer.ChatStatus.COMPLETED,
        }
        if chat_status and chat_status not in valid_statuses:
            raise ValidationError(
                {
                    "status": (
                        "status는 IN_REVIEW 또는 COMPLETED여야 합니다."
                    )
                }
            )

        queryset = (
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

        if chat_status == CaseChatRoomListSerializer.ChatStatus.COMPLETED:
            return queryset.filter(
                agreement__status=CaseAgreement.Status.FINAL,
            )
        if chat_status == CaseChatRoomListSerializer.ChatStatus.IN_REVIEW:
            return queryset.exclude(
                agreement__status=CaseAgreement.Status.FINAL,
            )
        return queryset


class CaseChatRoomReadView(APIView):
    permission_classes = [IsHospital]

    @transaction.atomic
    def post(self, request, room_id):
        chat_room = get_object_or_404(
            CaseChatRoom.objects.select_related(
                "medical_case",
                "medical_case__origin_hospital",
                "partner_hospital",
            ),
            id=room_id,
            is_active=True,
        )

        if request.user.id not in {
            chat_room.medical_case.origin_hospital_id,
            chat_room.partner_hospital_id,
        }:
            raise PermissionDenied(
                "해당 협진 채팅방에 접근할 권한이 없습니다."
            )

        last_read_message_id = request.data.get("last_read_message_id")
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
                hospital=request.user,
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
            read_state.save(update_fields=["last_read_message", "updated_at"])

        remaining_unread_count = chat_room.messages.exclude(
            sender=request.user,
        )
        if read_state.last_read_message_id is not None:
            remaining_unread_count = remaining_unread_count.filter(
                id__gt=read_state.last_read_message_id,
            )

        return Response(
            {
                "room_id": chat_room.id,
                "last_read_message_id": read_state.last_read_message_id,
                "read_at": read_state.updated_at,
                "unread_count": remaining_unread_count.count(),
            },
            status=status.HTTP_200_OK,
        )
