import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..exceptions import DuplicateCaseActionError
from ..models import (
    CaseAgreement,
    CaseChatRoom,
    CaseTransfer,
)
from ..selectors.agreement_queries import (
    get_agreement_chat_room_queryset,
    get_agreement_detail_queryset,
    get_agreement_revisions,
)
from ..services import (
    SUPPORTED_AGREEMENT_LANGUAGES,
    generate_case_agreement,
)
from ..services.agreement_service import (
    build_additional_opinion_translation_values,
    edit_case_agreement,
    review_case_agreement,
)
from ..serializers import (
    CaseAgreementSerializer,
    CaseAgreementRevisionSerializer,
)

logger = logging.getLogger(__name__)


def get_agreement_chat_room(request, case_id, room_id):
    if request.user.user_type != "HOSPITAL":
        raise PermissionDenied("병원 회원만 이용할 수 있습니다.")

    chat_room = get_object_or_404(
        get_agreement_chat_room_queryset(),
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


class CaseAgreementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        agreement = get_object_or_404(
            get_agreement_detail_queryset(),
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
            raise DuplicateCaseActionError(
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

        agreement, changed_fields = edit_case_agreement(
            chat_room=chat_room,
            hospital=request.user,
            data=request.data,
            request=request,
        )

        response_data = CaseAgreementSerializer(
            agreement,
            context={"request": request},
        ).data
        response_data["changed_fields"] = changed_fields

        return Response(response_data)



class CaseAgreementReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        agreement = review_case_agreement(
            chat_room=chat_room,
            hospital=request.user,
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

        revisions = get_agreement_revisions(agreement)

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
            raise DuplicateCaseActionError(
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
                raise DuplicateCaseActionError(
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
