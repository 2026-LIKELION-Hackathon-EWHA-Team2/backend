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
from accounts.models import User

from .models import (
    CaseAgreement,
    CaseTransfer,
    CaseAgreementReview,
    CaseAgreementRevision,
    CaseChatMessageTranslation,
    CaseChatRoom,
    CaseCollaborationRequest,
    CaseSyncRequest,
    MedicalCase,
)
from .services import (
    generate_case_agreement,
    translate_medical_message,
    translate_and_structure_transfer,
)



from .permissions import IsCaseChatParticipant, IsPatient, IsHospital
from .serializers import (
    CaseTransferCreateSerializer,
    CaseTransferDetailSerializer,
    CaseTransferReviewSerializer,
    PartnerCaseTransferSerializer,
    CaseAgreementSerializer,
    CaseAgreementRevisionSerializer,
    AdverseEffectUpdateSerializer,
    CaseChatMessageSerializer,
    CaseCollaborationRequestSerializer,
    CaseCollaborationRequestDetailSerializer,
    CaseTransferSerializer,
    MedicalCaseCreateSerializer,
    MedicalCaseDetailSerializer,
    CaseSyncRequestCreateSerializer,
    CaseSyncRequestDetailSerializer,
)

logger = logging.getLogger(__name__)

def get_collaboration_requests_for_user(user):
    return (
        CaseCollaborationRequest.objects
        .filter(
            Q(
                medical_case__origin_hospital=user,
            )
            | Q(
                medical_case__partner_hospital=user,
            )
        )
        .select_related(
            "medical_case",
            "medical_case__patient",
            "medical_case__origin_hospital",
            "medical_case__partner_hospital",
            "medical_case__sync_request",
            "medical_case__sync_request__patient",
            "medical_case__sync_request__origin_hospital",
            "medical_case__sync_request__partner_hospital",
            "medical_case__sync_request__symptom_case",
            "medical_case__sync_request__symptom_case__patient",
            "medical_case__sync_request__symptom_case__patient__user",
        )
        .prefetch_related(
            "medical_case__ingredients",
            "medical_case__adverse_effects",
            "medical_case__chat_rooms",
            "medical_case__sync_request__symptom_case__images",
            "medical_case__sync_request__symptom_case__areas",
            "medical_case__sync_request__symptom_case__symptom_types",
        )
        .order_by("-requested_at")
    )

def get_agreement_chat_room(request, case_id, room_id):
    if request.user.user_type != "HOSPITAL":
        raise PermissionDenied("병원 회원만 이용할 수 있습니다.")

    chat_room = get_object_or_404(
        CaseChatRoom.objects.select_related(
            "medical_case",
            "medical_case__origin_hospital",
            "partner_hospital",
        ),
        id=room_id,
        medical_case_id=case_id,
    )

    participant_ids = {
        chat_room.medical_case.origin_hospital_id,
        chat_room.partner_hospital_id,
    }

    if request.user.id not in participant_ids:
        raise PermissionDenied(
            "해당 협진 합의에 접근할 권한이 없습니다."
        )

    return chat_room



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

    ALLOWED_STATUSES = {
        CaseCollaborationRequest.Status.REQUESTED,
        CaseCollaborationRequest.Status.ACCEPTED,
    }

    def get_queryset(self):
        queryset = get_collaboration_requests_for_user(
            self.request.user,
        )

        status_value = (
            self.request.query_params.get("status")
        )

        if status_value is None:
            return queryset

        status_value = status_value.upper()

        if status_value not in self.ALLOWED_STATUSES:
            raise ValidationError(
                {
                    "status": (
                        "현재 조회 가능한 상태는 "
                        "REQUESTED 또는 ACCEPTED입니다."
                    )
                }
            )

        return queryset.filter(
            status=status_value,
        )


class CaseCollaborationRequestDetailView(
    generics.RetrieveAPIView
):
    permission_classes = [IsHospital]
    serializer_class = (
        CaseCollaborationRequestDetailSerializer
    )
    lookup_url_kwarg = (
        "collaboration_request_id"
    )

    def get_queryset(self):
        return get_collaboration_requests_for_user(
            self.request.user,
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

class CaseAgreementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        agreement = get_object_or_404(
            CaseAgreement.objects
            .select_related("edited_by", "chat_room")
            .prefetch_related(
                "reviews__hospital",
                "revisions",
            ),
            chat_room=chat_room,
        )

        serializer = CaseAgreementSerializer(
            agreement,
            context={"request": request},
        )
        return Response(serializer.data)

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        if CaseAgreement.objects.filter(
            chat_room=chat_room
        ).exists():
            raise ValidationError(
                "이미 생성된 협진 합의안이 있습니다."
            )

        serializer = CaseAgreementSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        agreement = serializer.save(
            chat_room=chat_room,
            status=CaseAgreement.Status.AI_DRAFT,
        )

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        with transaction.atomic():
            agreement = get_object_or_404(
                CaseAgreement.objects.select_for_update(),
                chat_room=chat_room,
            )

            if agreement.status == CaseAgreement.Status.FINAL:
                raise ValidationError(
                    "최종 합의 내용은 수정 요청 후 변경할 수 있습니다."
                )

            serializer = CaseAgreementSerializer(
                agreement,
                data=request.data,
                partial=True,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)

            editable_fields = (
                "judgment_draft",
                "evidence_items",
                "observation_days",
                "photo_upload_date",
                "follow_up_date",
                "precautions",
                "patient_message",
            )

            changed_fields = [
                field
                for field in editable_fields
                if field in serializer.validated_data
                and getattr(agreement, field)
                != serializer.validated_data[field]
            ]

            if not changed_fields:
                return Response(
                    CaseAgreementSerializer(
                        agreement,
                        context={"request": request},
                    ).data
                )

            def date_value(value):
                return (
                    value.isoformat()
                    if hasattr(value, "isoformat")
                    else value
                )

            previous_data = {
                field: date_value(getattr(agreement, field))
                for field in editable_fields
            }

            CaseAgreementRevision.objects.create(
                agreement=agreement,
                version=agreement.version,
                previous_data=previous_data,
                changed_fields=changed_fields,
                edited_by=request.user,
            )

            agreement = serializer.save(
                version=agreement.version + 1,
                status=CaseAgreement.Status.IN_REVIEW,
                edited_by=request.user,
                edited_at=timezone.now(),
                finalized_at=None,
            )

            # 수정되면 양측의 기존 검토를 모두 무효화합니다.
            agreement.reviews.all().delete()

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data
        )

class CaseAgreementReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        with transaction.atomic():
            agreement = get_object_or_404(
                CaseAgreement.objects.select_for_update(),
                chat_room=chat_room,
            )

            if agreement.status == CaseAgreement.Status.FINAL:
                raise ValidationError(
                    "이미 최종 합의가 완료되었습니다."
                )

            CaseAgreementReview.objects.update_or_create(
                agreement=agreement,
                hospital=request.user,
                defaults={
                    "reviewed_version": agreement.version,
                    "reviewed_at": timezone.now(),
                },
            )

            participant_ids = {
                chat_room.medical_case.origin_hospital_id,
                chat_room.partner_hospital_id,
            }

            reviewed_ids = set(
                agreement.reviews.filter(
                    reviewed_version=agreement.version,
                ).values_list("hospital_id", flat=True)
            )

            if reviewed_ids == participant_ids:
                agreement.status = CaseAgreement.Status.FINAL
                agreement.finalized_at = timezone.now()
            else:
                agreement.status = CaseAgreement.Status.IN_REVIEW

            agreement.save(
                update_fields=(
                    "status",
                    "finalized_at",
                    "updated_at",
                )
            )

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data
        )

class CaseAgreementRevisionRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        with transaction.atomic():
            agreement = get_object_or_404(
                CaseAgreement.objects.select_for_update(),
                chat_room=chat_room,
            )

            if agreement.status != CaseAgreement.Status.FINAL:
                raise ValidationError(
                    "최종 합의 상태에서만 수정 요청할 수 있습니다."
                )

            agreement.reviews.all().delete()

            agreement.status = CaseAgreement.Status.IN_REVIEW
            agreement.finalized_at = None
            agreement.revision_requested_by = request.user
            agreement.revision_requested_at = timezone.now()

            agreement.save(
                update_fields=(
                    "status",
                    "finalized_at",
                    "revision_requested_by",
                    "revision_requested_at",
                    "updated_at",
                )
            )

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data
        )

class CaseAgreementRevisionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        agreement = get_object_or_404(
            CaseAgreement,
            chat_room=chat_room,
        )

        revisions = (
            agreement.revisions
            .select_related("edited_by")
            .order_by("-version")
        )

        serializer = CaseAgreementRevisionSerializer(
            revisions,
            many=True,
        )

        return Response(
            {
                "agreement_id": agreement.id,
                "current_version": agreement.version,
                "revisions": serializer.data,
            }
        )

class CaseAgreementGenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        if CaseAgreement.objects.filter(
            chat_room=chat_room,
        ).exists():
            raise ValidationError(
                "이미 생성된 협진 합의안이 있습니다."
            )

        messages = list(
            chat_room.messages
            .select_related("sender")
            .order_by("id")
        )

        if not messages:
            raise ValidationError(
                "합의안을 생성할 채팅 메시지가 없습니다."
            )

        medical_case = chat_room.medical_case

        case_data = {
            "procedure_name": medical_case.procedure_name,
            "procedure_area": medical_case.procedure_area,
            "procedure_date": (
                medical_case.procedure_date.isoformat()
            ),
            "ingredients": list(
                medical_case.ingredients.values_list(
                    "ingredient_name",
                    flat=True,
                )
            ),
            "adverse_effects": list(
                medical_case.adverse_effects.values_list(
                    "effect_type",
                    flat=True,
                )
            ),
            "clinician_note": medical_case.clinician_note,
        }

        try:
            generated_data = generate_case_agreement(
                case_data=case_data,
                messages=messages,
            )
        except Exception:
            logger.exception(
                "OpenAI agreement generation failed"
            )
            raise ValidationError(
                "AI 합의안 초안을 생성하지 못했습니다."
            )

        serializer = CaseAgreementSerializer(
            data=generated_data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        # AI 호출 중 다른 요청이 합의안을 만들었는지 재확인합니다.
        with transaction.atomic():
            locked_room = (
                CaseChatRoom.objects
                .select_for_update()
                .get(id=chat_room.id)
            )

            if CaseAgreement.objects.filter(
                chat_room=locked_room,
            ).exists():
                raise ValidationError(
                    "이미 생성된 협진 합의안이 있습니다."
                )

            agreement = serializer.save(
                chat_room=locked_room,
                status=CaseAgreement.Status.AI_DRAFT,
                version=1,
            )

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class CaseTransferListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CaseTransferCreateSerializer
        return CaseTransferDetailSerializer

    def get_queryset(self):
        return (
            CaseTransfer.objects
            .filter(patient=self.request.user)
            .select_related(
                "patient",
                "partner_hospital",
                "symptom_case",
                "medical_case",
            )
            .order_by("-created_at")
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer = serializer.save()

        try:
            result = translate_and_structure_transfer(transfer)
            transfer.translated_data = result
            transfer.structured_data = result
            transfer.status = CaseTransfer.Status.REVIEW_REQUIRED
            transfer.processing_error = ""
        except Exception as exc:
            transfer.status = CaseTransfer.Status.PROCESSING_FAILED
            transfer.processing_error = str(exc)

        transfer.save(
            update_fields=[
                "translated_data",
                "structured_data",
                "status",
                "processing_error",
                "updated_at",
            ]
        )

        return Response(
            CaseTransferDetailSerializer(transfer).data,
            status=status.HTTP_201_CREATED,
        )


class CaseTransferDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CaseTransferDetailSerializer
    lookup_url_kwarg = "transfer_id"

    def get_queryset(self):
        return CaseTransfer.objects.filter(
            patient=self.request.user,
        ).select_related(
            "partner_hospital",
            "medical_case",
            "medical_case__origin_hospital",
        )


class CaseTransferReviewView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CaseTransferReviewSerializer
    lookup_url_kwarg = "transfer_id"
    http_method_names = ["patch"]

    def get_queryset(self):
        return CaseTransfer.objects.filter(
            patient=self.request.user,
        )


class CaseTransferSendView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, transfer_id):
        transfer = get_object_or_404(
            CaseTransfer.objects.select_for_update(),
            id=transfer_id,
            patient=request.user,
        )

        if transfer.status != CaseTransfer.Status.READY_TO_TRANSFER:
            return Response(
                {"detail": "전송 준비가 완료되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not all([
            transfer.procedure_medication_agreed,
            transfer.adverse_effect_clinician_note_agreed,
            transfer.overseas_ai_processing_agreed,
        ]):
            return Response(
                {"detail": "필수 동의가 완료되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not any([
            transfer.include_patient_info,
            transfer.include_procedure_info,
            transfer.include_adverse_effects,
            transfer.include_clinician_note,
        ]):
            return Response(
                {"detail": "전송 항목을 하나 이상 선택해야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transfer.status = CaseTransfer.Status.TRANSFERRED
        transfer.transferred_at = timezone.now()
        transfer.save(
            update_fields=[
                "status",
                "transferred_at",
                "updated_at",
            ]
        )

        return Response(
            CaseTransferDetailSerializer(transfer).data,
            status=status.HTTP_200_OK,
        )


class PartnerCaseTransferListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartnerCaseTransferSerializer

    def get_queryset(self):
        user = self.request.user

        if user.user_type != User.UserType.HOSPITAL:
            return CaseTransfer.objects.none()

        return (
            CaseTransfer.objects
            .filter(
                partner_hospital=user,
                status=CaseTransfer.Status.TRANSFERRED,
            )
            .select_related(
                "partner_hospital",
                "medical_case",
                "medical_case__origin_hospital",
            )
            .order_by("-transferred_at")
        )


class PartnerCaseTransferDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartnerCaseTransferSerializer
    lookup_url_kwarg = "transfer_id"

    def get_queryset(self):
        user = self.request.user

        if user.user_type != User.UserType.HOSPITAL:
            return CaseTransfer.objects.none()

        return (
            CaseTransfer.objects
            .filter(
                partner_hospital=user,
                status=CaseTransfer.Status.TRANSFERRED,
            )
            .select_related(
                "partner_hospital",
                "medical_case",
                "medical_case__origin_hospital",
            )
        )
