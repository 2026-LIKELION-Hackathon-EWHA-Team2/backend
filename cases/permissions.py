from rest_framework.permissions import BasePermission
from .models import MedicalCase


class IsPatient(BasePermission):
    message = "환자 회원만 이용할 수 있습니다."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type == "PATIENT"
        )


class IsHospital(BasePermission):
    message = "병원 회원만 이용할 수 있습니다."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type == "HOSPITAL"
        )

def check_chat_room_access(request, chat_room):
    user = request.user

    if user.user_type != "HOSPITAL":
        raise PermissionDenied(
            "병원 회원만 채팅을 이용할 수 있습니다."
        )

    origin_hospital_id = (
        chat_room.medical_case.origin_hospital_id
    )
    partner_hospital_id = chat_room.partner_hospital_id

    if user.id not in {
        origin_hospital_id,
        partner_hospital_id,
    }:
        raise PermissionDenied(
            "해당 채팅방에 접근할 권한이 없습니다."
        )

    if not chat_room.is_active:
        raise PermissionDenied(
            "종료된 협진 채팅방입니다."
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