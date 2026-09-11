from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ..models import (
    CaseChatReadState,
    CaseChatRoom,
    CaseCollaborationRequest,
    CaseTransfer,
    MedicalCase,
)


@transaction.atomic
def accept_collaboration_request(*, collaboration_request_id, hospital):
    collaboration_request = get_object_or_404(
        CaseCollaborationRequest.objects
        .select_for_update(of=("self",))
        .select_related(
            "medical_case",
            "medical_case__origin_hospital",
            "medical_case__partner_hospital",
        ),
        id=collaboration_request_id,
    )
    medical_case = collaboration_request.medical_case

    if medical_case.partner_hospital_id != hospital.id:
        raise PermissionDenied(
            "해당 협진 요청을 수락할 권한이 없습니다."
        )

    if medical_case.status != MedicalCase.Status.TRANSFERRED:
        raise ValidationError(
            {
                "detail": (
                    "환자의 의료정보 전송 동의가 "
                    "완료되지 않은 케이스입니다."
                )
            }
        )

    if collaboration_request.status == CaseCollaborationRequest.Status.ACCEPTED:
        chat_room = CaseChatRoom.objects.filter(
            medical_case=medical_case,
            partner_hospital=hospital,
        ).first()
        if chat_room is None:
            raise ValidationError(
                {
                    "detail": (
                        "수락된 요청이지만 채팅방이 존재하지 않습니다."
                    )
                }
            )
        return collaboration_request, chat_room, False

    if collaboration_request.status != CaseCollaborationRequest.Status.REQUESTED:
        raise ValidationError(
            {
                "detail": (
                    "현재 상태에서는 협진 요청을 수락할 수 없습니다."
                )
            }
        )

    chat_room, chat_room_created = CaseChatRoom.objects.get_or_create(
        medical_case=medical_case,
        partner_hospital=hospital,
        defaults={"is_active": True},
    )
    if not chat_room.is_active:
        raise ValidationError(
            {"detail": "해당 케이스의 채팅방이 비활성화된 상태입니다."}
        )

    for hospital_id in {
        medical_case.origin_hospital_id,
        hospital.id,
    }:
        CaseChatReadState.objects.get_or_create(
            chat_room=chat_room,
            hospital_id=hospital_id,
        )

    collaboration_request.status = CaseCollaborationRequest.Status.ACCEPTED
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
        symptom_case.status = symptom_case.Status.IN_COLLABORATION
        symptom_case.save(update_fields=["status", "updated_at"])

    return collaboration_request, chat_room, chat_room_created
