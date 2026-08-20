import re
from datetime import date

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
import logging
from django.db import transaction
from django.utils import timezone

from django.conf import settings
from accounts.models import User
from selfsymptoms.models import DiagnosisAnalysis, PatientSymptomCase

from .models import (
    CaseAgreement,
    CaseTransfer,
    CaseAgreementReview,
    CaseAgreementRevision,
    CaseIngredient,
    CaseChatMessageTranslation,
    CaseChatMessage,
    CaseChatReadState,
    CaseChatRoom,
    CaseCollaborationRequest,
    MedicalCase,
)
from .services import (
    SUPPORTED_AGREEMENT_LANGUAGES,
    analyze_diagnosis_document,
    generate_case_agreement,
    generate_patient_symptom_translation_summary,
    normalize_agreement_language,
    translate_case_agreement_content,
    translate_case_agreement_opinion,
    translate_medical_message,
)



from .permissions import IsCaseChatParticipant, IsHospital, IsPatient
from .serializers import (
    CaseTransferCreateSerializer,
    CaseTransferDetailSerializer,
    CaseTransferListSerializer,
    CaseTransferReviewSerializer,
    PartnerCaseTransferSerializer,
    CaseAgreementSerializer,
    CaseAgreementRevisionSerializer,
    CaseChatMessageSerializer,
    CaseChatRoomListSerializer,
    CaseCollaborationRequestDetailSerializer,
    CaseCollaborationRequestSerializer,
    MedicalCaseDetailSerializer,
    PatientProcedureHistoryDetailSerializer,
    PatientProcedureHistoryListSerializer,
    get_agreement_language_content,
)

logger = logging.getLogger(__name__)


def build_additional_opinion_translation_values(
    additional_opinion,
    source_language,
):
    if not additional_opinion:
        return {
            "additional_opinion_source_language": "",
            "additional_opinion_translations": {},
            "additional_opinion_translation_status": (
                CaseAgreement.OpinionTranslationStatus.NOT_REQUESTED
            ),
            "additional_opinion_translation_error_code": "",
        }

    source_language = normalize_agreement_language(source_language)

    try:
        translations = translate_case_agreement_opinion(
            additional_opinion,
            source_language,
        )
    except Exception:
        logger.exception("Case agreement opinion translation failed")
        return {
            "additional_opinion_source_language": source_language,
            "additional_opinion_translations": {
                source_language: additional_opinion,
            },
            "additional_opinion_translation_status": (
                CaseAgreement.OpinionTranslationStatus.FAILED
            ),
            "additional_opinion_translation_error_code": (
                "OPENAI_TRANSLATION_FAILED"
            ),
        }

    return {
        "additional_opinion_source_language": source_language,
        "additional_opinion_translations": translations,
        "additional_opinion_translation_status": (
            CaseAgreement.OpinionTranslationStatus.COMPLETED
        ),
        "additional_opinion_translation_error_code": "",
    }

def get_collaboration_requests_for_participating_hospital(user):
    """원 병원 또는 협진 병원으로 참여한 협진 요청을 반환합니다."""
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
        )
        .prefetch_related(
            "medical_case__ingredients",
            "medical_case__chat_rooms",
            "medical_case__case_transfers",
            "medical_case__case_transfers__symptom_case__images",
        )
        .order_by("-requested_at")
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


def get_received_collaboration_requests_for_user(user):
    return (
        CaseCollaborationRequest.objects
        .filter(
            medical_case__partner_hospital=user,
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



class MedicalCaseListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MedicalCaseDetailSerializer

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


class PatientProcedureHistoryListView(generics.ListAPIView):
    permission_classes = [IsPatient]
    serializer_class = PatientProcedureHistoryListSerializer

    def get_queryset(self):
        return (
            MedicalCase.objects
            .filter(
                patient=self.request.user,
                case_transfers__symptom_case__status=(
                    PatientSymptomCase.Status.COMPLETED
                ),
            )
            .select_related(
                "origin_hospital",
                "origin_hospital__hospital_profile",
            )
            .prefetch_related(
                Prefetch(
                    "case_transfers",
                    queryset=(
                        CaseTransfer.objects
                        .filter(
                            symptom_case__status=(
                                PatientSymptomCase.Status.COMPLETED
                            )
                        )
                        .select_related("symptom_case")
                    ),
                    to_attr="completed_case_transfers",
                )
            )
            .annotate(
                finalized_at=Max(
                    "chat_rooms__agreement__finalized_at",
                    filter=Q(
                        chat_rooms__agreement__status=(
                            CaseAgreement.Status.FINAL
                        )
                    ),
                )
            )
            .order_by("-procedure_date", "-id")
            .distinct()
        )


class PatientProcedureHistoryDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPatient]
    serializer_class = PatientProcedureHistoryDetailSerializer
    lookup_url_kwarg = "medical_case_id"

    def get_queryset(self):
        final_chat_rooms = (
            CaseChatRoom.objects
            .filter(
                agreement__status=CaseAgreement.Status.FINAL,
                agreement__finalized_at__isnull=False,
            )
            .select_related(
                "partner_hospital",
                "agreement",
            )
            .prefetch_related(
                Prefetch(
                    "agreement__reviews",
                    queryset=(
                        CaseAgreementReview.objects
                        .select_related("hospital")
                        .order_by("reviewed_at", "id")
                    ),
                )
            )
            .order_by("-agreement__finalized_at", "-id")
        )

        return (
            MedicalCase.objects
            .filter(
                patient=self.request.user,
                case_transfers__symptom_case__status=(
                    PatientSymptomCase.Status.COMPLETED
                ),
                chat_rooms__agreement__status=(
                    CaseAgreement.Status.FINAL
                ),
                chat_rooms__agreement__finalized_at__isnull=False,
            )
            .select_related(
                "origin_hospital",
                "origin_hospital__hospital_profile",
                "partner_hospital",
            )
            .prefetch_related(
                Prefetch(
                    "case_transfers",
                    queryset=(
                        CaseTransfer.objects
                        .filter(
                            symptom_case__status=(
                                PatientSymptomCase.Status.COMPLETED
                            )
                        )
                        .select_related("symptom_case")
                        .order_by("id")
                    ),
                    to_attr="completed_case_transfers",
                ),
                Prefetch(
                    "chat_rooms",
                    queryset=final_chat_rooms,
                    to_attr="final_agreement_chat_rooms",
                ),
            )
            .distinct()
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
        CaseCollaborationRequest.Status.COMPLETED,
    }

    def get_queryset(self):
        queryset = get_collaboration_requests_for_participating_hospital(
            self.request.user,
        )

        status_value = (
            self.request.query_params.get("status")
        )

        if status_value is not None:
            status_value = status_value.upper()

            if status_value not in self.ALLOWED_STATUSES:
                raise ValidationError(
                    {
                        "status": (
                            "현재 조회 가능한 상태는 "
                            "REQUESTED, ACCEPTED 또는 "
                            "COMPLETED입니다."
                        )
                    }
                )

            queryset = queryset.filter(status=status_value)

        search = self.request.query_params.get("search", "").strip()
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


class HospitalDashboardView(APIView):
    permission_classes = [IsHospital]

    def get(self, request):
        today = timezone.localdate()
        participating_requests = (
            get_collaboration_requests_for_participating_hospital(
                request.user,
            )
        )

        ongoing_collaborations = participating_requests.filter(
            status=CaseCollaborationRequest.Status.ACCEPTED,
        ).order_by("-accepted_at", "-requested_at")

        return Response(
            {
                "date": today,
                "today_summary": {
                    "new_request_count": participating_requests.filter(
                        status=CaseCollaborationRequest.Status.REQUESTED,
                        requested_at__date=today,
                    ).count(),
                    "in_review_count": participating_requests.filter(
                        status=CaseCollaborationRequest.Status.ACCEPTED,
                        accepted_at__date=today,
                    ).count(),
                    "completed_count": participating_requests.filter(
                        status=CaseCollaborationRequest.Status.COMPLETED,
                        completed_at__date=today,
                    ).count(),
                },
                "total_unread_count": (
                    get_total_unread_count_for_hospital(request.user)
                ),
                "ongoing_collaborations": (
                    CaseCollaborationRequestSerializer(
                        ongoing_collaborations,
                        many=True,
                        context={"request": request},
                    ).data
                ),
            },
            status=status.HTTP_200_OK,
        )


class CaseCollaborationRequestDetailView(
    generics.RetrieveAPIView
):
    """협진에 참여한 원 병원과 협진 병원이 요청 상세를 조회합니다."""

    permission_classes = [IsHospital]
    serializer_class = CaseCollaborationRequestDetailSerializer
    lookup_url_kwarg = (
        "collaboration_request_id"
    )

    def get_queryset(self):
        return get_collaboration_requests_for_participating_hospital(
            self.request.user,
        )



class CaseCollaborationRequestAcceptView(APIView):
    permission_classes = [IsHospital]

    @transaction.atomic
    def post(self, request, collaboration_request_id):
        collaboration_request = get_object_or_404(
            CaseCollaborationRequest.objects
            # Lock only the request row. PostgreSQL rejects FOR UPDATE when
            # it also targets the nullable partner-hospital outer join.
            .select_for_update(of=("self",))
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

        for hospital_id in {
            medical_case.origin_hospital_id,
            request.user.id,
        }:
            CaseChatReadState.objects.get_or_create(
                chat_room=chat_room,
                hospital_id=hospital_id,
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

        transfer = (
            CaseTransfer.objects
            .select_related("symptom_case")
            .filter(
                medical_case=medical_case,
                status=CaseTransfer.Status.TRANSFERRED,
            )
            .first()
        )
        if transfer is not None:
            symptom_case = transfer.symptom_case
            symptom_case.status = (
                symptom_case.Status.IN_COLLABORATION
            )
            symptom_case.save(
                update_fields=["status", "updated_at"]
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

        opinion_translation_values = (
            build_additional_opinion_translation_values(
                serializer.validated_data.get(
                    "additional_opinion",
                    "",
                ),
                request.user.preferred_language,
            )
        )

        agreement = serializer.save(
            chat_room=chat_room,
            status=CaseAgreement.Status.AI_DRAFT,
            **opinion_translation_values,
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
                    {
                        "detail": (
                            "최종 합의가 완료된 후에는 "
                            "수정할 수 없습니다."
                        )
                    }
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
                "additional_opinion",
            )

            source_language = normalize_agreement_language(
                request.user.preferred_language
            )
            current_localized = get_agreement_language_content(
                agreement,
                source_language,
            )
            current_values = {
                "judgment_draft": current_localized[
                    "judgment_draft"
                ],
                "evidence_items": current_localized[
                    "evidence_items"
                ],
                "additional_opinion": agreement.additional_opinion,
            }

            changed_fields = [
                field
                for field in editable_fields
                if field in serializer.validated_data
                and current_values[field]
                != serializer.validated_data[field]
            ]

            if not changed_fields:
                response_data = CaseAgreementSerializer(
                    agreement,
                    context={"request": request},
                ).data
                response_data["changed_fields"] = []
                return Response(response_data)

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

            save_values = {}
            localized_fields_changed = any(
                field in changed_fields
                for field in (
                    "judgment_draft",
                    "evidence_items",
                )
            )

            if localized_fields_changed:
                candidate_judgment = serializer.validated_data.get(
                    "judgment_draft",
                    current_values["judgment_draft"],
                )
                candidate_evidence = serializer.validated_data.get(
                    "evidence_items",
                    current_values["evidence_items"],
                )
                try:
                    localized_content = (
                        translate_case_agreement_content(
                            candidate_judgment,
                            candidate_evidence,
                            source_language,
                        )
                    )
                except Exception:
                    logger.exception(
                        "Case agreement content translation failed"
                    )
                    localized_content = {
                        source_language: {
                            "judgment_draft": candidate_judgment,
                            "evidence_items": candidate_evidence,
                        }
                    }

                canonical_content = localized_content.get(
                    "ko",
                    localized_content[source_language],
                )
                save_values.update(
                    {
                        "judgment_draft": canonical_content[
                            "judgment_draft"
                        ],
                        "evidence_items": canonical_content[
                            "evidence_items"
                        ],
                        "localized_content": localized_content,
                    }
                )

            if "additional_opinion" in changed_fields:
                save_values.update(
                    build_additional_opinion_translation_values(
                        serializer.validated_data[
                            "additional_opinion"
                        ],
                        source_language,
                    )
                )

            agreement = serializer.save(
                version=agreement.version + 1,
                status=CaseAgreement.Status.IN_REVIEW,
                edited_by=request.user,
                edited_at=timezone.now(),
                finalized_at=None,
                **save_values,
            )

            # 먼저 완료한 병원의 확인은 이후 편집에도 유효합니다.
            # 따라서 두 번째 병원이 최종 완료하면 재검토 없이
            # 곧바로 최종 합의가 됩니다.
            agreement.reviews.update(
                reviewed_version=agreement.version,
            )

        response_data = CaseAgreementSerializer(
            agreement,
            context={"request": request},
        ).data
        response_data["changed_fields"] = changed_fields

        return Response(response_data)


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

def complete_case_agreement(agreement, chat_room):
    completed_at = timezone.now()
    agreement.status = CaseAgreement.Status.FINAL
    agreement.finalized_at = completed_at
    agreement.revision_requested_by = None
    agreement.revision_requested_at = None
    agreement.save(
        update_fields=(
            "status",
            "finalized_at",
            "revision_requested_by",
            "revision_requested_at",
            "updated_at",
        )
    )

    collaboration_request = (
        CaseCollaborationRequest.objects
        .filter(medical_case=chat_room.medical_case)
        .first()
    )
    if collaboration_request is not None:
        collaboration_request.status = (
            CaseCollaborationRequest.Status.COMPLETED
        )
        collaboration_request.completed_at = completed_at
        collaboration_request.save(
            update_fields=(
                "status",
                "completed_at",
                "updated_at",
            )
        )

    transfer = (
        chat_room.medical_case.case_transfers
        .select_related("symptom_case")
        .filter(status=CaseTransfer.Status.TRANSFERRED)
        .first()
    )
    if transfer is not None:
        symptom_case = transfer.symptom_case
        symptom_case.status = symptom_case.Status.COMPLETED
        symptom_case.save(
            update_fields=["status", "updated_at"]
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
                complete_case_agreement(agreement, chat_room)
            else:
                agreement.status = CaseAgreement.Status.IN_REVIEW
                agreement.save(
                    update_fields=(
                        "status",
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
                {
                    "detail": (
                        "이미 생성된 협진 합의안이 있습니다."
                    )
                }
            )

        messages = list(
            chat_room.messages
            .select_related("sender")
            .order_by("id")
        )

        medical_case = chat_room.medical_case
        case_transfer = (
            medical_case.case_transfers
            .filter(status=CaseTransfer.Status.TRANSFERRED)
            .first()
        )
        adverse_effects = (
            case_transfer.adverse_effects
            if case_transfer is not None
            else []
        )

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
            "adverse_effects": adverse_effects,
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
            return Response(
                {
                    "detail": (
                        "AI 합의안 초안을 생성하지 못했습니다."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        localized_content = {
            language: {
                "judgment_draft": generated_data[language][
                    "judgment_draft"
                ],
                "evidence_items": generated_data[language][
                    "evidence_items"
                ],
            }
            for language in SUPPORTED_AGREEMENT_LANGUAGES
            if (
                isinstance(generated_data.get(language), dict)
                and "judgment_draft" in generated_data[language]
                and "evidence_items" in generated_data[language]
            )
        }

        if localized_content:
            canonical_content = (
                localized_content.get("ko")
                or next(iter(localized_content.values()))
            )
            generated_data = dict(canonical_content)
        else:
            # 기존 호출자와 테스트 payload는 한국어 원본으로 호환합니다.
            localized_content = {
                "ko": {
                    "judgment_draft": generated_data.get(
                        "judgment_draft",
                        "",
                    ),
                    "evidence_items": generated_data.get(
                        "evidence_items",
                        [],
                    ),
                }
            }

        # 추가 소견은 AI가 아니라 참여 의료진이 직접 작성합니다.
        generated_data["additional_opinion"] = ""

        serializer = CaseAgreementSerializer(
            data=generated_data,
            context={"request": request},
        )
        if not serializer.is_valid():
            logger.error(
                "Invalid AI agreement payload: %s",
                serializer.errors,
            )
            return Response(
                {
                    "detail": (
                        "AI 합의안 초안을 생성하지 못했습니다."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

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
                    {
                        "detail": (
                            "이미 생성된 협진 합의안이 있습니다."
                        )
                    }
                )

            agreement = serializer.save(
                chat_room=locked_room,
                status=CaseAgreement.Status.AI_DRAFT,
                version=1,
                localized_content=localized_content,
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

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsPatient()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CaseTransferListSerializer
        return CaseTransferCreateSerializer

    def get_queryset(self):
        return (
            CaseTransfer.objects
            .filter(
                patient=self.request.user,
                status__in=(
                    CaseTransfer.Status.REVIEW_REQUIRED,
                    CaseTransfer.Status.READY_TO_TRANSFER,
                ),
            )
            .select_related(
                "recommendation",
                "partner_hospital",
                "medical_case",
                "medical_case__origin_hospital",
            )
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        symptom_case = serializer.validated_data["symptom_case"]
        recommendation = serializer.validated_data["recommendation"]
        partner_hospital = recommendation.hospital.user

        symptom_data = {
            "description": symptom_case.description,
            "start_date": (
                symptom_case.symptom_start_date.isoformat()
                if symptom_case.symptom_start_date
                else None
            ),
            "onset_timing": symptom_case.get_onset_timing_display()
            if symptom_case.onset_timing
            else None,
            "pain_level": symptom_case.pain_level,
            "areas": [
                area.get_area_type_display()
                for area in symptom_case.areas.all()
            ],
            "types": [
                symptom_type.custom_symptom
                or symptom_type.get_symptom_type_display()
                for symptom_type in symptom_case.symptom_types.all()
            ],
        }

        try:
            document_result = analyze_diagnosis_document(
                symptom_case.diagnosis_document,
                partner_hospital.hospital_profile.language_code,
                symptom_data,
            )
        except Exception as exc:
            logger.exception("Diagnosis document analysis failed")
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        procedure = document_result["procedure"]
        try:
            procedure_date = date.fromisoformat(procedure["date"])
        except (TypeError, ValueError):
            return Response(
                {
                    "detail": (
                        "진단서에서 추출한 시술일 형식이 "
                        "올바르지 않습니다."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            ai_summary = generate_patient_symptom_translation_summary(
                symptom_data,
                partner_hospital.hospital_profile.language_code,
            )
        except Exception as exc:
            logger.exception("Case translation summary generation failed")
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        translated_symptoms = document_result.get("symptoms") or {}
        patient_birth_date = serializer.validated_data.get(
            "patient_birth_date"
        )
        structured_data = {
            "patient_info": {
                "name": serializer.validated_data["patient_name"],
                "gender": serializer.validated_data.get(
                    "patient_gender"
                ),
                "birth_date": (
                     patient_birth_date.isoformat()
                     if patient_birth_date
                     else None
                ),
            },
            "symptoms": {
                "description": (
                    translated_symptoms.get("description")
                    or symptom_data["description"]
                ),
                "start_date": (
                    translated_symptoms.get("start_date")
                    or symptom_data["start_date"]
                ),
                "onset_timing": (
                    translated_symptoms.get("onset_timing")
                    or symptom_data["onset_timing"]
                ),
                "pain_level": (
                    translated_symptoms.get("pain_level")
                    if translated_symptoms.get("pain_level") is not None
                    else symptom_data["pain_level"]
                ),
                "areas": (
                    translated_symptoms.get("areas")
                    or symptom_data["areas"]
                ),
                "types": (
                    translated_symptoms.get("types")
                    or symptom_data["types"]
                ),
                "images": list(
                    symptom_case.images.values_list(
                        "image",
                        flat=True,
                    )
                ),
            },
            "procedure": procedure,
            "ingredients": document_result["ingredients"],
            "clinician_note": document_result["clinician_note"],
            "ai_summary": ai_summary,
        }

        with transaction.atomic():
            DiagnosisAnalysis.objects.update_or_create(
                symptom_case=symptom_case,
                defaults={
                    "extracted_text": document_result[
                        "extracted_text"
                    ],
                    "analysis_result": {
                        key: value
                        for key, value in document_result.items()
                        if key != "extracted_text"
                    },
                    "analyzed_at": timezone.now(),
                },
            )

            medical_case = MedicalCase.objects.create(
                patient=request.user,
                origin_hospital=(
                    symptom_case.diagnosed_hospital.user
                ),
                partner_hospital=partner_hospital,
                procedure_name=procedure["name"],
                procedure_area=procedure["area"],
                procedure_date=procedure_date,
                clinician_note=document_result["clinician_note"],
                ai_summary=ai_summary,
                status=MedicalCase.Status.READY_TO_TRANSFER,
            )

            CaseIngredient.objects.bulk_create(
                [
                    CaseIngredient(
                        medical_case=medical_case,
                        ingredient_name=ingredient,
                    )
                    for ingredient
                    in dict.fromkeys(document_result["ingredients"])
                ]
            )

            transfer = serializer.save(
                medical_case=medical_case,
                structured_data=structured_data,
                translated_data={},
                status=CaseTransfer.Status.REVIEW_REQUIRED,
                processing_error="",
            )

        return Response(
            CaseTransferDetailSerializer(transfer).data,
            status=status.HTTP_201_CREATED,
        )


class CaseTransferDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPatient]
    serializer_class = CaseTransferDetailSerializer
    lookup_url_kwarg = "transfer_id"

    def get_queryset(self):
        return CaseTransfer.objects.filter(
            patient=self.request.user,
            status__in=(
                CaseTransfer.Status.REVIEW_REQUIRED,
                CaseTransfer.Status.READY_TO_TRANSFER,
            ),
        ).select_related(
            "recommendation",
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

    def patch(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(
            transfer,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        transfer = serializer.save()

        return Response(
            CaseTransferDetailSerializer(transfer).data,
            status=status.HTTP_200_OK,
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

        medical_case = transfer.medical_case
        medical_case.partner_hospital = transfer.partner_hospital
        medical_case.status = MedicalCase.Status.TRANSFERRED
        medical_case.transferred_at = transfer.transferred_at
        medical_case.save(
            update_fields=[
                "partner_hospital",
                "status",
                "transferred_at",
                "updated_at",
            ]
        )

        CaseCollaborationRequest.objects.get_or_create(
            medical_case=medical_case,
            defaults={
                "status": CaseCollaborationRequest.Status.REQUESTED,
            },
        )

        symptom_case = transfer.symptom_case
        symptom_case.status = symptom_case.Status.CONNECTION_REQUESTED
        symptom_case.save(
            update_fields=["status", "updated_at"]
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
                "medical_case__collaboration_request",
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
                "medical_case__collaboration_request",
            )
        )
