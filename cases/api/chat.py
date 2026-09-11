from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import CaseAgreement
from ..permissions import IsCaseChatParticipant, IsHospital
from ..selectors.chat_queries import (
    get_chat_messages,
    get_chat_room_queryset,
    get_chat_rooms_for_hospital,
)
from ..services.chat_service import (
    create_chat_message,
    mark_chat_room_read,
)
from ..serializers import (
    CaseChatMessageSerializer,
    CaseChatRoomListSerializer,
)

class CaseChatMessageListCreateView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsCaseChatParticipant,
    ]

    def get_chat_room(self, request, case_id, room_id):
        chat_room = get_object_or_404(
            get_chat_room_queryset(),
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

        messages = get_chat_messages(chat_room)

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

        message = create_chat_message(
            chat_room=chat_room,
            sender=request.user,
            validated_data=serializer.validated_data,
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

        queryset = get_chat_rooms_for_hospital(user)

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

    def post(self, request, room_id):
        chat_room, read_state, remaining_unread_count = (
            mark_chat_room_read(
                room_id=room_id,
                hospital=request.user,
                last_read_message_id=request.data.get(
                    "last_read_message_id"
                ),
            )
        )

        return Response(
            {
                "room_id": chat_room.id,
                "last_read_message_id": read_state.last_read_message_id,
                "read_at": read_state.updated_at,
                "unread_count": remaining_unread_count,
            },
            status=status.HTTP_200_OK,
        )
