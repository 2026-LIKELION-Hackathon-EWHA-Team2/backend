from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import CaseCollaborationRequest
from ..permissions import IsHospital
from ..selectors.chat_queries import get_total_unread_count_for_hospital
from ..selectors.collaboration_queries import (
    filter_collaboration_requests,
    get_collaboration_requests_for_participating_hospital,
)
from ..services.collaboration_service import accept_collaboration_request
from ..serializers import (
    CaseCollaborationRequestDetailSerializer,
    CaseCollaborationRequestSerializer,
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

    def post(self, request, collaboration_request_id):
        collaboration_request, chat_room, chat_room_created = (
            accept_collaboration_request(
                collaboration_request_id=collaboration_request_id,
                hospital=request.user,
            )
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
