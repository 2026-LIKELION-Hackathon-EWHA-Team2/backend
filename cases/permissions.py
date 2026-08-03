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