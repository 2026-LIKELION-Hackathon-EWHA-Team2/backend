from rest_framework.permissions import BasePermission


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