from rest_framework.permissions import BasePermission

from accounts.permissions import IsHospital

from .models import MedicalCase


class IsMedicalCaseParticipant(BasePermission):
    message = "해당 케이스를 조회할 권한이 없습니다."

    def has_object_permission(self, request, view, medical_case):
        is_patient = medical_case.patient_id == request.user.id
        is_origin = medical_case.origin_hospital_id == request.user.id
        is_partner = (
            medical_case.partner_hospital_id == request.user.id
            and medical_case.status == MedicalCase.Status.TRANSFERRED
        )

        return is_patient or is_origin or is_partner


class IsCaseAgreementParticipant(IsHospital):
    message = "해당 협진 합의에 접근할 권한이 없습니다."

    def has_object_permission(self, request, view, chat_room):
        return request.user.id in {
            chat_room.medical_case.origin_hospital_id,
            chat_room.partner_hospital_id,
        }


class IsCaseChatParticipant(IsHospital):
    message = "해당 협진 채팅방에 접근할 권한이 없습니다."

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
