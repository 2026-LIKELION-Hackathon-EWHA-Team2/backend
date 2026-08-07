from django.shortcuts import render

# Create your views here.
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import logging

from django.conf import settings

from .models import (
    CaseChatMessageTranslation,
    CaseChatRoom,
    MedicalCase,
)
from .services import translate_medical_message


from .permissions import IsCaseChatParticipant, IsPatient
from .serializers import (
    AdverseEffectUpdateSerializer,
    CaseChatMessageSerializer,
    CaseTransferSerializer,
    MedicalCaseCreateSerializer,
    MedicalCaseDetailSerializer,
)

logger = logging.getLogger(__name__)



class MedicalCaseListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MedicalCaseCreateSerializer

        return MedicalCaseDetailSerializer

    def get_queryset(self):
        user = self.request.user

        if user.user_type == "PATIENT":
            return MedicalCase.objects.filter(
                patient=user
            )

        if user.user_type == "HOSPITAL":
            return MedicalCase.objects.filter(
                Q(origin_hospital=user)
                | Q(
                    partner_hospital=user,
                    status=MedicalCase.Status.TRANSFERRED,
                )
            ).distinct()

        return MedicalCase.objects.none()

    def create(self, request, *args, **kwargs):
        if request.user.user_type != "HOSPITAL":
            raise PermissionDenied(
                "병원 회원만 케이스를 생성할 수 있습니다."
            )

        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        medical_case = serializer.save(
            origin_hospital=request.user,
        )

        return Response(
            MedicalCaseDetailSerializer(
                medical_case
            ).data,
            status=status.HTTP_201_CREATED,
        )


class MedicalCaseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id):
        medical_case = get_object_or_404(
            MedicalCase.objects.select_related(
                "patient",
                "origin_hospital",
                "partner_hospital",
            ).prefetch_related(
                "ingredients",
                "adverse_effects",
            ),
            id=case_id,
        )

        is_patient = (
            medical_case.patient_id
            == request.user.id
        )
        is_origin = (
            medical_case.origin_hospital_id
            == request.user.id
        )
        is_partner = (
            medical_case.partner_hospital_id
            == request.user.id
            and medical_case.status
            == MedicalCase.Status.TRANSFERRED
        )

        if not (
            is_patient
            or is_origin
            or is_partner
        ):
            raise PermissionDenied(
                "해당 케이스를 조회할 권한이 없습니다."
            )

        return Response(
            MedicalCaseDetailSerializer(
                medical_case
            ).data
        )


class AdverseEffectUpdateView(APIView):
    permission_classes = [IsPatient]

    def put(self, request, case_id):
        medical_case = get_object_or_404(
            MedicalCase,
            id=case_id,
            patient=request.user,
        )

        serializer = AdverseEffectUpdateSerializer(
            data=request.data,
            context={
                "medical_case": medical_case,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            MedicalCaseDetailSerializer(
                medical_case
            ).data
        )


class CaseTransferView(APIView):
    permission_classes = [IsPatient]

    def post(self, request, case_id):
        medical_case = get_object_or_404(
            MedicalCase,
            id=case_id,
            patient=request.user,
        )

        serializer = CaseTransferSerializer(
            medical_case,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            MedicalCaseDetailSerializer(
                medical_case
            ).data
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