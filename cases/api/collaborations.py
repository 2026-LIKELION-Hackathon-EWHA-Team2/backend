import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    CaseTransfer,
    CaseChatReadState,
    CaseChatRoom,
    CaseCollaborationRequest,
    MedicalCase,
)
from ..permissions import IsHospital
from ..selectors.chat_queries import get_total_unread_count_for_hospital
from ..selectors.collaboration_queries import (
    filter_collaboration_requests,
    get_collaboration_requests_for_participating_hospital,
)
from ..serializers import (
    CaseCollaborationRequestDetailSerializer,
    CaseCollaborationRequestSerializer,
)

logger = logging.getLogger(__name__)


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

        return filter_collaboration_requests(
            queryset,
            status_value=status_value,
            search=self.request.query_params.get("search", ""),
        )


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
