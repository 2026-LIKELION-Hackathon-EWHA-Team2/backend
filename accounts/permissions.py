from rest_framework.permissions import BasePermission

from .models import User


class HasUserType(BasePermission):
    """Allow authenticated users whose role is explicitly supported."""

    allowed_user_types = frozenset()

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type in self.allowed_user_types
        )


class IsPatient(HasUserType):
    message = "환자 계정만 접근할 수 있습니다."
    allowed_user_types = frozenset({User.UserType.PATIENT})


class IsHospital(HasUserType):
    message = "병원 계정만 접근할 수 있습니다."
    allowed_user_types = frozenset({User.UserType.HOSPITAL})


class IsPatientOrHospital(HasUserType):
    message = "환자 또는 병원 계정만 접근할 수 있습니다."
    allowed_user_types = frozenset(
        {
            User.UserType.PATIENT,
            User.UserType.HOSPITAL,
        }
    )
