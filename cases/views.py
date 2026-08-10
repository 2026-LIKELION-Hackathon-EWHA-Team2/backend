from django.shortcuts import render

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import logging
from django.db import transaction
from django.utils import timezone

from django.conf import settings

from .models import (
    CaseChatMessageTranslation,
    CaseChatRoom,
    CaseCollaborationRequest,
    CaseSyncRequest,
    MedicalCase,
)
from .services import translate_medical_message




from .permissions import IsCaseChatParticipant, IsPatient, IsHospital
from .serializers import (
    AdverseEffectUpdateSerializer,
    CaseChatMessageSerializer,
    CaseCollaborationRequestSerializer,
    CaseTransferSerializer,
    MedicalCaseCreateSerializer,
    MedicalCaseDetailSerializer,
    CaseSyncRequestCreateSerializer,
    CaseSyncRequestDetailSerializer,
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

    @transaction.atomic
    def post(self, request, case_id):
        medical_case = get_object_or_404(
            MedicalCase.objects.select_for_update(),
            id=case_id,
            patient=request.user,
        )

        serializer = CaseTransferSerializer(
            medical_case,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        collaboration_request, request_created = (
            CaseCollaborationRequest.objects.get_or_create(
                medical_case=medical_case,
                defaults={
                    "status": (
                        CaseCollaborationRequest.Status.REQUESTED
                    ),
                },
            )
        )

        CaseSyncRequest.objects.filter(
            medical_case=medical_case,
        ).update(
            status=CaseSyncRequest.Status.SENT_TO_PARTNER,
            updated_at=timezone.now(),
        )

        response_data = dict(
            MedicalCaseDetailSerializer(
                medical_case,
            ).data
        )

        response_data.update(
            {
                "collaboration_request_id": (
                    collaboration_request.id
                ),
                "collaboration_request_status": (
                    collaboration_request.status
                ),
                "collaboration_request_created": (
                    request_created
                ),
            }
        )

        return Response(
            response_data,
            status=status.HTTP_200_OK,
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


class CaseSyncRequestListCreateView(
    generics.ListCreateAPIView
):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CaseSyncRequestCreateSerializer

        return CaseSyncRequestDetailSerializer

    def get_queryset(self):
        user = self.request.user

        queryset = (
            CaseSyncRequest.objects
            .select_related(
                "patient",
                "symptom_case",
                "symptom_case__patient",
                "symptom_case__patient__user",
                "origin_hospital",
                "partner_hospital",
                "medical_case",
            )
            .prefetch_related(
                "symptom_case__images",
                "symptom_case__areas",
                "symptom_case__symptom_types",
            )
            .order_by("-created_at")
        )

        if user.user_type == "PATIENT":
            return queryset.filter(
                patient=user,
            )

        if user.user_type == "HOSPITAL":
            return queryset.filter(
                origin_hospital=user,
            )

        return queryset.none()

    def perform_create(self, serializer):
        serializer.save(
            patient=self.request.user,
        )


class CaseSyncRequestReviewView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, sync_request_id):
        sync_request = get_object_or_404(
            CaseSyncRequest.objects
            .select_for_update()
            .select_related(
                "patient",
                "symptom_case",
                "origin_hospital",
                "partner_hospital",
            ),
            id=sync_request_id,
        )

        if request.user.user_type != "HOSPITAL":
            raise PermissionDenied(
                "병원 회원만 검토할 수 있습니다."
            )

        if request.user != sync_request.origin_hospital:
            raise PermissionDenied(
                "해당 시술 병원만 검토할 수 있습니다."
            )

        if (
            sync_request.status
            != CaseSyncRequest.Status.REQUESTED
        ):
            return Response(
                {
                    "detail": (
                        "이미 검토됐거나 "
                        "처리할 수 없는 요청입니다."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        case_data = {
            **request.data,
            "patient_id": sync_request.patient_id,
            "partner_hospital_id": (
                sync_request.partner_hospital_id
            ),
        }

        case_serializer = MedicalCaseCreateSerializer(
            data=case_data,
            context={"request": request},
        )
        case_serializer.is_valid(raise_exception=True)

        medical_case = case_serializer.save(
            origin_hospital=request.user,
        )

        sync_request.medical_case = medical_case
        sync_request.status = (
            CaseSyncRequest.Status.HOSPITAL_REVIEWED
        )
        sync_request.reviewed_at = timezone.now()

        sync_request.save(
            update_fields=[
                "medical_case",
                "status",
                "reviewed_at",
                "updated_at",
            ]
        )

        return Response(
            {
                "sync_request": (
                    CaseSyncRequestDetailSerializer(
                        sync_request,
                        context={"request": request},
                    ).data
                ),
                "medical_case": (
                    MedicalCaseDetailSerializer(
                        medical_case
                    ).data
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class CaseCollaborationRequestListView(
    generics.ListAPIView
):
    permission_classes = [IsHospital]
    serializer_class = (
        CaseCollaborationRequestSerializer
    )

    def get_queryset(self):
        return (
            CaseCollaborationRequest.objects
            .filter(
                medical_case__partner_hospital=(
                    self.request.user
                ),
            )
            .select_related(
                "medical_case",
                "medical_case__patient",
                "medical_case__origin_hospital",
                "medical_case__partner_hospital",
            )
            .prefetch_related(
                "medical_case__ingredients",
                "medical_case__adverse_effects",
                "medical_case__chat_rooms",
            )
        )


class CaseCollaborationRequestAcceptView(APIView):
    permission_classes = [IsHospital]

    @transaction.atomic
    def post(self, request, collaboration_request_id):
        collaboration_request = get_object_or_404(
            CaseCollaborationRequest.objects
            .select_for_update()
            .select_related(
                "medical_case",
                "medical_case__origin_hospital",
                "medical_case__partner_hospital",
            ),
            id=collaboration_request_id,
        )

        medical_case = (
            collaboration_request.medical_case
        )

        if (
            medical_case.partner_hospital_id
            != request.user.id
        ):
            raise PermissionDenied(
                "해당 협진 요청을 수락할 권한이 없습니다."
            )

        if (
            medical_case.status
            != MedicalCase.Status.TRANSFERRED
        ):
            raise ValidationError(
                {
                    "detail": (
                        "환자의 의료정보 전송 동의가 "
                        "완료되지 않은 케이스입니다."
                    )
                }
            )

        # 같은 요청을 다시 보낸 경우 기존 채팅방 반환
        if (
            collaboration_request.status
            == CaseCollaborationRequest.Status.ACCEPTED
        ):
            chat_room = CaseChatRoom.objects.filter(
                medical_case=medical_case,
                partner_hospital=request.user,
            ).first()

            if chat_room is None:
                raise ValidationError(
                    {
                        "detail": (
                            "수락된 요청이지만 채팅방이 "
                            "존재하지 않습니다."
                        )
                    }
                )

            return Response(
                {
                    "collaboration_request": (
                        CaseCollaborationRequestSerializer(
                            collaboration_request,
                            context={"request": request},
                        ).data
                    ),
                    "chat_room_id": chat_room.id,
                    "chat_room_created": False,
                },
                status=status.HTTP_200_OK,
            )

        if (
            collaboration_request.status
            != CaseCollaborationRequest.Status.REQUESTED
        ):
            raise ValidationError(
                {
                    "detail": (
                        "현재 상태에서는 협진 요청을 "
                        "수락할 수 없습니다."
                    )
                }
            )

        # 협진 수락 트랜잭션 안에서 채팅방 생성
        chat_room, chat_room_created = (
            CaseChatRoom.objects.get_or_create(
                medical_case=medical_case,
                partner_hospital=request.user,
                defaults={
                    "is_active": True,
                },
            )
        )

        if not chat_room.is_active:
            raise ValidationError(
                {
                    "detail": (
                        "해당 케이스의 채팅방이 "
                        "비활성화된 상태입니다."
                    )
                }
            )

        collaboration_request.status = (
            CaseCollaborationRequest.Status.ACCEPTED
        )
        collaboration_request.accepted_at = timezone.now()
        collaboration_request.save(
            update_fields=[
                "status",
                "accepted_at",
                "updated_at",
            ]
        )

        CaseSyncRequest.objects.filter(
            medical_case=medical_case,
        ).update(
            status=CaseSyncRequest.Status.COMPLETED,
            updated_at=timezone.now(),
        )

        return Response(
            {
                "collaboration_request": (
                    CaseCollaborationRequestSerializer(
                        collaboration_request,
                        context={"request": request},
                    ).data
                ),
                "chat_room_id": chat_room.id,
                "chat_room_created": chat_room_created,
            },
            status=status.HTTP_200_OK,
        )