from datetime import date

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from .models import (
    CaseAdverseEffect,
    CaseIngredient,
    MedicalCase,
)


class MedicalCaseAPITests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="patient1",
            password="TestPassword!2026",
            name="홍길동",
            user_type=User.UserType.PATIENT,
        )

        self.other_patient = User.objects.create_user(
            username="patient2",
            password="TestPassword!2026",
            name="김환자",
            user_type=User.UserType.PATIENT,
        )

        self.origin_hospital = User.objects.create_user(
            username="origin-hospital",
            password="TestPassword!2026",
            name="서울병원",
            user_type=User.UserType.HOSPITAL,
        )

        self.partner_hospital = User.objects.create_user(
            username="partner-hospital",
            password="TestPassword!2026",
            name="Tokyo Medical",
            user_type=User.UserType.HOSPITAL,
        )

        self.other_hospital = User.objects.create_user(
            username="other-hospital",
            password="TestPassword!2026",
            name="다른병원",
            user_type=User.UserType.HOSPITAL,
        )

    def create_case(
        self,
        status_value=MedicalCase.Status.WAITING_PATIENT,
    ):
        medical_case = MedicalCase.objects.create(
            patient=self.patient,
            origin_hospital=self.origin_hospital,
            partner_hospital=self.partner_hospital,
            procedure_name="보톡스",
            procedure_area="이마",
            procedure_date=date(2026, 8, 1),
            clinician_note="시술 후 경과 관찰이 필요합니다.",
            status=status_value,
        )

        CaseIngredient.objects.create(
            medical_case=medical_case,
            ingredient_name="Botulinum Toxin Type A",
        )

        return medical_case

    def test_hospital_can_create_case(self):
        self.client.force_authenticate(
            user=self.origin_hospital
        )

        request_data = {
            "patient_id": self.patient.id,
            "partner_hospital_id": self.partner_hospital.id,
            "procedure_name": "보톡스",
            "procedure_area": "이마",
            "procedure_date": "2026-08-01",
            "ingredients": [
                "Botulinum Toxin Type A",
                "Lidocaine HCl",
            ],
            "clinician_note": "시술 후 경과 관찰이 필요합니다.",
        }

        response = self.client.post(
            reverse("case-list-create"),
            request_data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        medical_case = MedicalCase.objects.get(
            id=response.data["id"]
        )

        self.assertEqual(
            medical_case.patient,
            self.patient,
        )
        self.assertEqual(
            medical_case.origin_hospital,
            self.origin_hospital,
        )
        self.assertEqual(
            medical_case.partner_hospital,
            self.partner_hospital,
        )
        self.assertEqual(
            medical_case.status,
            MedicalCase.Status.WAITING_PATIENT,
        )

        ingredient_names = list(
            medical_case.ingredients.values_list(
                "ingredient_name",
                flat=True,
            )
        )

        self.assertCountEqual(
            ingredient_names,
            [
                "Botulinum Toxin Type A",
                "Lidocaine HCl",
            ],
        )

    def test_patient_cannot_create_case(self):
        self.client.force_authenticate(user=self.patient)

        request_data = {
            "patient_id": self.patient.id,
            "partner_hospital_id": self.partner_hospital.id,
            "procedure_name": "보톡스",
            "procedure_area": "이마",
            "procedure_date": "2026-08-01",
            "ingredients": [
                "Botulinum Toxin Type A",
            ],
            "clinician_note": "테스트 소견",
        }

        response = self.client.post(
            reverse("case-list-create"),
            request_data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_patient_can_view_own_case(self):
        medical_case = self.create_case()

        self.client.force_authenticate(user=self.patient)

        response = self.client.get(
            reverse(
                "case-detail",
                kwargs={"case_id": medical_case.id},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["patient_name"],
            "홍길동",
        )

    def test_other_patient_cannot_view_case(self):
        medical_case = self.create_case()

        self.client.force_authenticate(
            user=self.other_patient
        )

        response = self.client.get(
            reverse(
                "case-detail",
                kwargs={"case_id": medical_case.id},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_patient_can_update_adverse_effects(self):
        medical_case = self.create_case()

        self.client.force_authenticate(user=self.patient)

        response = self.client.put(
            reverse(
                "case-adverse-effects",
                kwargs={"case_id": medical_case.id},
            ),
            {
                "effect_types": [
                    CaseAdverseEffect.EffectType.SWELLING,
                    CaseAdverseEffect.EffectType.PAIN,
                ]
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        medical_case.refresh_from_db()

        self.assertEqual(
            medical_case.status,
            MedicalCase.Status.READY_TO_TRANSFER,
        )

        effect_types = list(
            medical_case.adverse_effects.values_list(
                "effect_type",
                flat=True,
            )
        )

        self.assertCountEqual(
            effect_types,
            [
                CaseAdverseEffect.EffectType.SWELLING,
                CaseAdverseEffect.EffectType.PAIN,
            ],
        )

    def test_other_patient_cannot_update_adverse_effects(self):
        medical_case = self.create_case()

        self.client.force_authenticate(
            user=self.other_patient
        )

        response = self.client.put(
            reverse(
                "case-adverse-effects",
                kwargs={"case_id": medical_case.id},
            ),
            {
                "effect_types": [
                    CaseAdverseEffect.EffectType.PAIN,
                ]
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_transfer_requires_all_consents(self):
        medical_case = self.create_case(
            status_value=MedicalCase.Status.READY_TO_TRANSFER
        )

        self.client.force_authenticate(user=self.patient)

        response = self.client.post(
            reverse(
                "case-transfer",
                kwargs={"case_id": medical_case.id},
            ),
            {
                "procedure_info_agreed": True,
                "adverse_effect_info_agreed": True,
                "overseas_transfer_agreed": False,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        medical_case.refresh_from_db()

        self.assertEqual(
            medical_case.status,
            MedicalCase.Status.READY_TO_TRANSFER,
        )
        self.assertIsNone(medical_case.transferred_at)

    def test_transfer_makes_case_visible_to_partner_hospital(self):
        medical_case = self.create_case(
            status_value=MedicalCase.Status.READY_TO_TRANSFER
        )

        # 전송 전에는 협진 병원이 조회할 수 없음
        self.client.force_authenticate(
            user=self.partner_hospital
        )

        before_response = self.client.get(
            reverse(
                "case-detail",
                kwargs={"case_id": medical_case.id},
            )
        )

        self.assertEqual(
            before_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # 환자가 전송 동의
        self.client.force_authenticate(user=self.patient)

        transfer_response = self.client.post(
            reverse(
                "case-transfer",
                kwargs={"case_id": medical_case.id},
            ),
            {
                "procedure_info_agreed": True,
                "adverse_effect_info_agreed": True,
                "overseas_transfer_agreed": True,
            },
            format="json",
        )

        self.assertEqual(
            transfer_response.status_code,
            status.HTTP_200_OK,
        )

        medical_case.refresh_from_db()

        self.assertEqual(
            medical_case.status,
            MedicalCase.Status.TRANSFERRED,
        )
        self.assertIsNotNone(
            medical_case.transferred_at
        )

        # 전송 후에는 협진 병원이 조회 가능
        self.client.force_authenticate(
            user=self.partner_hospital
        )

        after_response = self.client.get(
            reverse(
                "case-detail",
                kwargs={"case_id": medical_case.id},
            )
        )

        self.assertEqual(
            after_response.status_code,
            status.HTTP_200_OK,
        )

    def test_unrelated_hospital_cannot_view_transferred_case(self):
        medical_case = self.create_case(
            status_value=MedicalCase.Status.TRANSFERRED
        )

        self.client.force_authenticate(
            user=self.other_hospital
        )

        response = self.client.get(
            reverse(
                "case-detail",
                kwargs={"case_id": medical_case.id},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_transferred_case_cannot_update_adverse_effects(self):
        medical_case = self.create_case(
            status_value=MedicalCase.Status.TRANSFERRED
        )

        self.client.force_authenticate(user=self.patient)

        response = self.client.put(
            reverse(
                "case-adverse-effects",
                kwargs={"case_id": medical_case.id},
            ),
            {
                "effect_types": [
                    CaseAdverseEffect.EffectType.PAIN,
                ]
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_anonymous_user_cannot_access_case_list(self):
        response = self.client.get(
            reverse("case-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )