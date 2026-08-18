from rest_framework.permissions import BasePermission
from .models import MedicalCase


class IsHospital(BasePermission):
    message = "병원 회원만 이용할 수 있습니다."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type == "HOSPITAL"
        )


class IsPatient(BasePermission):
    message = "환자만 전송 Case를 조회할 수 있습니다."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type == "PATIENT"
        )


class IsCaseChatParticipant(BasePermission):
    message = "해당 협진 채팅방에 접근할 권한이 없습니다."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type == "HOSPITAL"
        )

    def has_object_permission(self, request, view, chat_room):
        if not chat_room.is_active:
            return False

        if (
            chat_room.medical_case.status
            != MedicalCase.Status.TRANSFERRED
        ):
            return False

        return request.user.id in {
            chat_room.medical_case.origin_hospital_id,
            chat_room.partner_hospital_id,
        }
