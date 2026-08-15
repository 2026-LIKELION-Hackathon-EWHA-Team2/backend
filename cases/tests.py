from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import HospitalProfile, PatientProfile, User
from selfsymptoms.models import DiagnosisAnalysis, PatientSymptomCase
from .models import (
    CaseAgreement,
    CaseAgreementReview,
    CaseChatMessage,
    CaseChatRoom,
    MedicalCase,
    CaseAdverseEffect,
    CaseIngredient,
    CaseTransfer,
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

class CaseAgreementAPITests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="agreement-patient",
            password="TestPassword!2026",
            name="환자",
            user_type=User.UserType.PATIENT,
        )
        self.origin = User.objects.create_user(
            username="agreement-origin",
            password="TestPassword!2026",
            name="자국 병원",
            user_type=User.UserType.HOSPITAL,
        )
        self.partner = User.objects.create_user(
            username="agreement-partner",
            password="TestPassword!2026",
            name="Tokyo Medical",
            user_type=User.UserType.HOSPITAL,
        )
        self.outsider = User.objects.create_user(
            username="agreement-outsider",
            password="TestPassword!2026",
            name="다른 병원",
            user_type=User.UserType.HOSPITAL,
        )

        self.medical_case = MedicalCase.objects.create(
            patient=self.patient,
            origin_hospital=self.origin,
            partner_hospital=self.partner,
            procedure_name="레이저 시술",
            procedure_area="얼굴",
            procedure_date=date(2026, 8, 1),
            clinician_note="경과 관찰이 필요합니다.",
        )
        self.chat_room = CaseChatRoom.objects.create(
            medical_case=self.medical_case,
            partner_hospital=self.partner,
        )

        self.detail_url = reverse(
            "case-agreement-detail",
            kwargs={
                "case_id": self.medical_case.id,
                "room_id": self.chat_room.id,
            },
        )
        self.review_url = reverse(
            "case-agreement-review",
            kwargs={
                "case_id": self.medical_case.id,
                "room_id": self.chat_room.id,
            },
        )
        self.generate_url = reverse(
            "case-agreement-generate",
            kwargs={
                "case_id": self.medical_case.id,
                "room_id": self.chat_room.id,
            },
        )
        self.revision_request_url = reverse(
            "case-agreement-revision-request",
            kwargs={
                "case_id": self.medical_case.id,
                "room_id": self.chat_room.id,
            },
        )

        self.payload = {
            "judgment_draft": "경과 관찰이 필요합니다.",
            "evidence_items": [
                {
                    "id": "evidence-1",
                    "content": "부종 및 홍반이 경미함",
                    "order": 1,
                },
                {
                    "id": "evidence-2",
                    "content": "감염 징후 없음",
                    "order": 2,
                },
            ],
        }

    def create_agreement(self):
        self.client.force_authenticate(user=self.origin)
        return self.client.post(
            self.detail_url,
            self.payload,
            format="json",
        )

    def test_participant_can_create_ai_draft(self):
        response = self.create_agreement()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            response.data["status"],
            CaseAgreement.Status.AI_DRAFT,
        )
        self.assertEqual(response.data["version"], 1)
        self.assertEqual(response.data["additional_opinion"], "")
        self.assertIsNone(response.data["latest_edit"])
        self.assertNotIn("follow_up_actions", response.data)
        self.assertNotIn("precautions", response.data)
        self.assertNotIn("patient_message", response.data)

    def test_final_content_and_evidence_are_editable(self):
        self.create_agreement()

        updated_evidence = [
            {
                "id": "evidence-updated",
                "content": "No signs of infection were observed.",
                "order": 1,
            },
        ]
        response = self.client.patch(
            self.detail_url,
            {
                "judgment_draft": "Additional follow-up is recommended.",
                "evidence_items": updated_evidence,
            },
            format="json",
        )

        agreement = CaseAgreement.objects.get(
            chat_room=self.chat_room,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            agreement.judgment_draft,
            "Additional follow-up is recommended.",
        )
        self.assertEqual(
            agreement.evidence_items[0]["content"],
            "No signs of infection were observed.",
        )
        self.assertEqual(
            response.data["changed_fields"],
            ["judgment_draft", "evidence_items"],
        )

    def test_doctor_can_write_additional_opinion(self):
        self.create_agreement()

        response = self.client.patch(
            self.detail_url,
            {
                "additional_opinion": (
                    "Monitor the patient for one more week."
                ),
            },
            format="json",
        )

        agreement = CaseAgreement.objects.get(
            chat_room=self.chat_room,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            agreement.additional_opinion,
            "Monitor the patient for one more week.",
        )
        self.assertEqual(
            response.data["additional_opinion"],
            "Monitor the patient for one more week.",
        )
        self.assertEqual(
            response.data["changed_fields"],
            ["additional_opinion"],
        )

        detail_response = self.client.get(self.detail_url)

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            detail_response.data["latest_edit"]["hospital_name"],
            self.origin.name,
        )
        self.assertIsNotNone(
            detail_response.data["latest_edit"]["edited_at"],
        )

    @patch("cases.views.generate_case_agreement")
    def test_ai_generation_leaves_additional_opinion_empty(self, generate):
        CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.origin,
            source_language="ko",
            content="감염 징후는 없습니다.",
        )
        generate.return_value = {
            "judgment_draft": "경과 관찰이 필요합니다.",
            "evidence_items": [],
            "additional_opinion": "AI가 생성하면 안 되는 내용",
        }

        self.client.force_authenticate(user=self.origin)
        response = self.client.post(self.generate_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["additional_opinion"], "")

    def test_unchanged_patch_returns_empty_changed_fields(self):
        self.create_agreement()

        response = self.client.patch(
            self.detail_url,
            {"judgment_draft": self.payload["judgment_draft"]},
            format="json",
        )

        agreement = CaseAgreement.objects.get(
            chat_room=self.chat_room,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["changed_fields"], [])
        self.assertEqual(agreement.version, 1)
        self.assertFalse(agreement.revisions.exists())

    def test_outside_hospital_cannot_read_agreement(self):
        self.create_agreement()
        self.client.force_authenticate(user=self.outsider)

        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_both_hospitals_review_to_finalize(self):
        self.create_agreement()

        first_response = self.client.post(
            self.review_url,
            format="json",
        )
        self.assertEqual(
            first_response.data["status"],
            CaseAgreement.Status.IN_REVIEW,
        )

        self.client.force_authenticate(user=self.partner)
        second_response = self.client.post(
            self.review_url,
            format="json",
        )

        self.assertEqual(
            second_response.data["status"],
            CaseAgreement.Status.FINAL,
        )
        self.assertIsNotNone(
            second_response.data["finalized_at"],
        )

    def test_edit_invalidates_existing_review(self):
        self.create_agreement()
        self.client.post(self.review_url, format="json")

        response = self.client.patch(
            self.detail_url,
            {
                "judgment_draft": "추가 진료를 권장합니다.",
            },
            format="json",
        )

        agreement = CaseAgreement.objects.get(
            chat_room=self.chat_room,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(agreement.version, 2)
        self.assertEqual(
            agreement.status,
            CaseAgreement.Status.IN_REVIEW,
        )
        self.assertFalse(agreement.reviews.exists())
        self.assertEqual(
            response.data["changed_fields"],
            ["judgment_draft"],
        )

    def test_final_agreement_requires_revision_request(self):
        self.create_agreement()
        self.client.post(self.review_url, format="json")

        self.client.force_authenticate(user=self.partner)
        self.client.post(self.review_url, format="json")

        blocked_response = self.client.patch(
            self.detail_url,
            {"judgment_draft": "수정 내용"},
            format="json",
        )
        self.assertEqual(
            blocked_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        request_response = self.client.post(
            self.revision_request_url,
            format="json",
        )
        self.assertEqual(
            request_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            request_response.data["status"],
            CaseAgreement.Status.IN_REVIEW,
        )

        edit_response = self.client.patch(
            self.detail_url,
            {"judgment_draft": "수정 내용"},
            format="json",
        )
        self.assertEqual(
            edit_response.status_code,
            status.HTTP_200_OK,
        )


class CaseTransferDocumentFlowTests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="document-patient",
            password="TestPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient,
            birth_date=date(1995, 3, 10),
            residence_country="KR",
        )
        self.origin = User.objects.create_user(
            username="document-origin",
            password="TestPassword!2026",
            name="Origin Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.origin_profile = HospitalProfile.objects.create(
            user=self.origin,
            country="KR",
            city="Seoul",
            address="Seoul",
            language_code="ko",
        )
        self.partner = User.objects.create_user(
            username="document-partner",
            password="TestPassword!2026",
            name="Partner Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        HospitalProfile.objects.create(
            user=self.partner,
            country="JP",
            city="Tokyo",
            address="Tokyo",
            language_code="ja",
        )
        self.symptom_case = PatientSymptomCase.objects.create(
            patient=self.patient_profile,
            diagnosed_hospital=self.origin_profile,
            diagnosis_document=SimpleUploadedFile(
                "diagnosis.pdf",
                b"test document",
                content_type="application/pdf",
            ),
            description="Swelling and pain",
            symptom_start_date=date(2026, 8, 10),
            pain_level=3,
            status=PatientSymptomCase.Status.HOSPITAL_SELECTED,
        )
        self.client.force_authenticate(user=self.patient)

    @patch("cases.views.analyze_diagnosis_document")
    def test_transfer_is_created_from_diagnosis_document(self, analyze):
        analyze.return_value = {
            "extracted_text": "diagnosis text",
            "symptoms": {
                "description": "Translated swelling and pain",
                "start_date": "2026-08-10",
                "onset_timing": None,
                "pain_level": 3,
                "areas": [],
                "types": [],
            },
            "procedure": {
                "name": "Botox",
                "area": "Forehead",
                "date": "2026-08-09",
            },
            "ingredients": ["Botulinum Toxin Type A"],
            "clinician_note": "Observe symptoms.",
        }

        response = self.client.post(
            reverse("case-transfer-list-create"),
            {
                "symptom_case_id": self.symptom_case.pk,
                "partner_hospital_id": self.partner.pk,
                "patient_name": "Patient",
                "patient_gender": CaseTransfer.Gender.OTHER,
                "patient_birth_date": "1995-03-10",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = CaseTransfer.objects.get(pk=response.data["id"])
        self.assertEqual(transfer.status, CaseTransfer.Status.REVIEW_REQUIRED)
        self.assertEqual(transfer.target_language, "ja")
        self.assertEqual(transfer.medical_case.origin_hospital, self.origin)
        self.assertEqual(transfer.medical_case.procedure_name, "Botox")
        self.assertEqual(
            transfer.structured_data["symptoms"]["description"],
            "Translated swelling and pain",
        )
        self.assertTrue(
            DiagnosisAnalysis.objects.filter(
                symptom_case=self.symptom_case,
            ).exists()
        )
        analyze.assert_called_once()

    def test_transfer_requires_diagnosis_document(self):
        self.symptom_case.diagnosis_document = None
        self.symptom_case.save(update_fields=["diagnosis_document"])

        response = self.client.post(
            reverse("case-transfer-list-create"),
            {
                "symptom_case_id": self.symptom_case.pk,
                "partner_hospital_id": self.partner.pk,
                "patient_name": "Patient",
                "patient_gender": CaseTransfer.Gender.OTHER,
                "patient_birth_date": "1995-03-10",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CaseTransfer.objects.exists())
