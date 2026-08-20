from datetime import date, timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import HospitalProfile, PatientProfile, User
from matching.models import HospitalMatchRequest, HospitalRecommendation
from selfsymptoms.models import DiagnosisAnalysis, PatientSymptomCase

from .models import (
    CaseAgreement,
    CaseAgreementReview,
    CaseChatMessage,
    CaseChatMessageTranslation,
    CaseChatReadState,
    CaseChatRoom,
    CaseCollaborationRequest,
    CaseTransfer,
    MedicalCase,
)


class MedicalCaseReadAPITests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="case-patient",
            password="TestPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        self.origin = User.objects.create_user(
            username="case-origin",
            password="TestPassword!2026",
            name="Origin Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.partner = User.objects.create_user(
            username="case-partner",
            password="TestPassword!2026",
            name="Partner Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.medical_case = MedicalCase.objects.create(
            patient=self.patient,
            origin_hospital=self.origin,
            partner_hospital=self.partner,
            procedure_name="Botox",
            procedure_area="Forehead",
            procedure_date=date(2026, 8, 1),
            clinician_note="Observe symptoms.",
            status=MedicalCase.Status.TRANSFERRED,
        )

    def test_participants_can_read_case(self):
        for user in (self.patient, self.origin, self.partner):
            self.client.force_authenticate(user=user)
            response = self.client.get(
                reverse(
                    "case-detail",
                    kwargs={"case_id": self.medical_case.id},
                )
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_medical_case_collection_is_read_only(self):
        self.client.force_authenticate(user=self.origin)

        response = self.client.post(
            reverse("case-list"),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class PatientProcedureHistoryListAPITests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="procedure-history-patient",
            password="TestPassword!2026",
            name="Anna Kim",
            user_type=User.UserType.PATIENT,
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient,
        )
        self.other_patient = User.objects.create_user(
            username="procedure-history-other-patient",
            password="TestPassword!2026",
            name="Other Patient",
            user_type=User.UserType.PATIENT,
        )
        self.other_patient_profile = PatientProfile.objects.create(
            user=self.other_patient,
        )
        self.origin = User.objects.create_user(
            username="procedure-history-origin",
            password="TestPassword!2026",
            name="ABC Beauty Clinic",
            user_type=User.UserType.HOSPITAL,
        )
        self.partner = User.objects.create_user(
            username="procedure-history-partner",
            password="TestPassword!2026",
            name="Tokyo Medical",
            user_type=User.UserType.HOSPITAL,
        )
        self.origin_profile = HospitalProfile.objects.create(
            user=self.origin,
            country="KR",
            city="Seoul",
            address="Gangnam",
        )
        self.partner_profile = HospitalProfile.objects.create(
            user=self.partner,
            country="JP",
            city="Tokyo",
            address="Chiyoda",
        )
        self.url = reverse("patient-procedure-history-list")

    def create_history_case(
        self,
        *,
        patient,
        patient_profile,
        symptom_status,
        procedure_name,
        procedure_date,
        agreement_status=None,
        finalized_at=None,
    ):
        symptom_case = PatientSymptomCase.objects.create(
            patient=patient_profile,
            status=symptom_status,
        )
        medical_case = MedicalCase.objects.create(
            patient=patient,
            origin_hospital=self.origin,
            partner_hospital=self.partner,
            procedure_name=procedure_name,
            procedure_area="이마",
            procedure_date=procedure_date,
            clinician_note="경과 관찰",
            status=MedicalCase.Status.TRANSFERRED,
        )
        CaseTransfer.objects.create(
            medical_case=medical_case,
            patient=patient,
            symptom_case=symptom_case,
            partner_hospital=self.partner,
            patient_name=patient.name,
            patient_gender=CaseTransfer.Gender.FEMALE,
            patient_birth_date=date(1992, 5, 20),
            target_language="ja",
            status=CaseTransfer.Status.TRANSFERRED,
        )

        if agreement_status is not None:
            chat_room = CaseChatRoom.objects.create(
                medical_case=medical_case,
                partner_hospital=self.partner,
            )
            CaseAgreement.objects.create(
                chat_room=chat_room,
                judgment_draft="경증 반응으로 판단됩니다.",
                evidence_items=[],
                status=agreement_status,
                finalized_at=finalized_at,
            )

        return symptom_case, medical_case

    def test_list_returns_only_own_completed_symptom_cases(self):
        finalized_at = timezone.now() - timedelta(hours=1)
        completed_symptom_case, completed_medical_case = (
            self.create_history_case(
                patient=self.patient,
                patient_profile=self.patient_profile,
                symptom_status=PatientSymptomCase.Status.COMPLETED,
                procedure_name="보톡스",
                procedure_date=date(2025, 8, 1),
                agreement_status=CaseAgreement.Status.FINAL,
                finalized_at=finalized_at,
            )
        )
        self.create_history_case(
            patient=self.patient,
            patient_profile=self.patient_profile,
            symptom_status=PatientSymptomCase.Status.IN_COLLABORATION,
            procedure_name="필러",
            procedure_date=date(2025, 9, 1),
            agreement_status=CaseAgreement.Status.IN_REVIEW,
        )
        self.create_history_case(
            patient=self.other_patient,
            patient_profile=self.other_patient_profile,
            symptom_status=PatientSymptomCase.Status.COMPLETED,
            procedure_name="레이저",
            procedure_date=date(2025, 10, 1),
            agreement_status=CaseAgreement.Status.FINAL,
            finalized_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.patient)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        item = response.data[0]
        self.assertEqual(
            item["medical_case_id"],
            completed_medical_case.id,
        )
        self.assertEqual(
            item["symptom_case_id"],
            completed_symptom_case.symptom_case_id,
        )
        self.assertEqual(item["status"], "COMPLETED")
        self.assertEqual(item["procedure_name"], "보톡스")
        self.assertEqual(item["procedure_area"], "이마")
        self.assertEqual(
            item["procedure_hospital_name"],
            "ABC Beauty Clinic",
        )
        self.assertEqual(item["procedure_hospital_country"], "KR")
        self.assertEqual(item["procedure_hospital_city"], "Seoul")
        self.assertEqual(
            item["finalized_at"],
            finalized_at.isoformat().replace("+00:00", "Z"),
        )

    def test_detail_returns_completed_final_history(self):
        finalized_at = timezone.now() - timedelta(hours=1)
        symptom_case, medical_case = self.create_history_case(
            patient=self.patient,
            patient_profile=self.patient_profile,
            symptom_status=PatientSymptomCase.Status.COMPLETED,
            procedure_name="보톡스",
            procedure_date=date(2025, 8, 1),
            agreement_status=CaseAgreement.Status.FINAL,
            finalized_at=finalized_at,
        )
        agreement = CaseAgreement.objects.get(
            chat_room__medical_case=medical_case,
        )
        agreement.evidence_items = [
            {
                "id": "evidence-1",
                "order": 1,
                "content": "부종이 경미합니다.",
            }
        ]
        agreement.additional_opinion = "경과 관찰이 필요합니다."
        agreement.save(
            update_fields=(
                "evidence_items",
                "additional_opinion",
                "updated_at",
            )
        )
        origin_review = CaseAgreementReview.objects.create(
            agreement=agreement,
            hospital=self.origin,
            reviewed_version=agreement.version,
        )
        partner_review = CaseAgreementReview.objects.create(
            agreement=agreement,
            hospital=self.partner,
            reviewed_version=agreement.version,
        )
        self.client.force_authenticate(user=self.patient)

        response = self.client.get(
            reverse(
                "patient-procedure-history-detail",
                kwargs={"medical_case_id": medical_case.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["medical_case_id"], medical_case.id)
        self.assertEqual(
            response.data["symptom_case_id"],
            symptom_case.symptom_case_id,
        )
        self.assertEqual(response.data["status"], "COMPLETED")
        self.assertEqual(response.data["procedure"]["name"], "보톡스")
        self.assertEqual(
            response.data["procedure"]["hospital_name"],
            "ABC Beauty Clinic",
        )
        self.assertEqual(
            response.data["procedure"]["hospital_country"],
            "KR",
        )
        self.assertEqual(
            response.data["procedure"]["hospital_city"],
            "Seoul",
        )
        self.assertEqual(
            response.data["collaboration"]["partner_hospital_name"],
            "Tokyo Medical",
        )
        final_agreement = response.data["final_agreement"]
        self.assertEqual(final_agreement["agreement_id"], agreement.id)
        self.assertEqual(final_agreement["status"], "FINAL")
        self.assertEqual(
            final_agreement["judgment_draft"],
            "경증 반응으로 판단됩니다.",
        )
        self.assertEqual(
            final_agreement["evidence_items"],
            agreement.evidence_items,
        )
        self.assertEqual(
            final_agreement["additional_opinion"],
            "경과 관찰이 필요합니다.",
        )
        self.assertEqual(
            [
                review["hospital_id"]
                for review in final_agreement["reviews"]
            ],
            [origin_review.hospital_id, partner_review.hospital_id],
        )

    def test_detail_hides_other_patients_history(self):
        _, medical_case = self.create_history_case(
            patient=self.other_patient,
            patient_profile=self.other_patient_profile,
            symptom_status=PatientSymptomCase.Status.COMPLETED,
            procedure_name="레이저",
            procedure_date=date(2025, 10, 1),
            agreement_status=CaseAgreement.Status.FINAL,
            finalized_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.patient)

        response = self.client.get(
            reverse(
                "patient-procedure-history-detail",
                kwargs={"medical_case_id": medical_case.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_hides_history_before_final_agreement(self):
        _, medical_case = self.create_history_case(
            patient=self.patient,
            patient_profile=self.patient_profile,
            symptom_status=PatientSymptomCase.Status.COMPLETED,
            procedure_name="필러",
            procedure_date=date(2025, 9, 1),
            agreement_status=CaseAgreement.Status.IN_REVIEW,
        )
        self.client.force_authenticate(user=self.patient)

        response = self.client.get(
            reverse(
                "patient-procedure-history-detail",
                kwargs={"medical_case_id": medical_case.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_hides_history_without_agreement(self):
        _, medical_case = self.create_history_case(
            patient=self.patient,
            patient_profile=self.patient_profile,
            symptom_status=PatientSymptomCase.Status.COMPLETED,
            procedure_name="필러",
            procedure_date=date(2025, 9, 1),
        )
        self.client.force_authenticate(user=self.patient)

        response = self.client.get(
            reverse(
                "patient-procedure-history-detail",
                kwargs={"medical_case_id": medical_case.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_hospital_cannot_read_patient_procedure_history_detail(self):
        _, medical_case = self.create_history_case(
            patient=self.patient,
            patient_profile=self.patient_profile,
            symptom_status=PatientSymptomCase.Status.COMPLETED,
            procedure_name="보톡스",
            procedure_date=date(2025, 8, 1),
            agreement_status=CaseAgreement.Status.FINAL,
            finalized_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.origin)

        response = self.client.get(
            reverse(
                "patient-procedure-history-detail",
                kwargs={"medical_case_id": medical_case.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_hospital_cannot_read_patient_procedure_history(self):
        self.client.force_authenticate(user=self.origin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class HospitalDashboardAndReceivedCaseTests(APITestCase):
    def setUp(self):
        self.hospital = User.objects.create_user(
            username="dashboard-hospital",
            password="TestPassword!2026",
            name="Tokyo Medical",
            user_type=User.UserType.HOSPITAL,
        )
        self.origin = User.objects.create_user(
            username="dashboard-origin",
            password="TestPassword!2026",
            name="Seoul Beauty Clinic",
            user_type=User.UserType.HOSPITAL,
        )
        self.other_hospital = User.objects.create_user(
            username="dashboard-other",
            password="TestPassword!2026",
            name="Osaka Clinic",
            user_type=User.UserType.HOSPITAL,
        )
        self.anna = User.objects.create_user(
            username="dashboard-anna",
            password="TestPassword!2026",
            name="Anna Kim",
            user_type=User.UserType.PATIENT,
        )
        self.sato = User.objects.create_user(
            username="dashboard-sato",
            password="TestPassword!2026",
            name="Sato Aoi",
            user_type=User.UserType.PATIENT,
        )
        self.client.force_authenticate(user=self.hospital)

    def create_request(
        self,
        patient,
        request_status,
        *,
        partner=None,
        requested_at=None,
        accepted_at=None,
        completed_at=None,
    ):
        medical_case = MedicalCase.objects.create(
            patient=patient,
            origin_hospital=self.origin,
            partner_hospital=partner or self.hospital,
            procedure_name="Botox",
            procedure_area="Forehead",
            procedure_date=date(2026, 8, 1),
            clinician_note="Observe symptoms.",
            status=MedicalCase.Status.TRANSFERRED,
        )
        collaboration_request = CaseCollaborationRequest.objects.create(
            medical_case=medical_case,
            status=request_status,
            accepted_at=accepted_at,
            completed_at=completed_at,
        )

        if requested_at is not None:
            CaseCollaborationRequest.objects.filter(
                pk=collaboration_request.pk,
            ).update(requested_at=requested_at)
            collaboration_request.refresh_from_db()

        return collaboration_request

    def test_case_lookup_returns_all_dates_and_filters_status(self):
        old_time = timezone.now() - timedelta(days=7)
        requested = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
        )
        completed = self.create_request(
            self.sato,
            CaseCollaborationRequest.Status.COMPLETED,
            requested_at=old_time,
            completed_at=old_time,
        )
        self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
            partner=self.other_hospital,
        )

        response = self.client.get(
            reverse("collaboration-request-list"),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in response.data},
            {requested.id, completed.id},
        )

        completed_response = self.client.get(
            reverse("collaboration-request-list"),
            {"status": "COMPLETED"},
        )
        self.assertEqual(len(completed_response.data), 1)
        self.assertEqual(completed_response.data[0]["id"], completed.id)

    def test_case_lookup_includes_origin_hospital_cases(self):
        visible_request = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        unrelated_case = MedicalCase.objects.create(
            patient=self.sato,
            origin_hospital=self.other_hospital,
            partner_hospital=self.hospital,
            procedure_name="Filler",
            procedure_area="Chin",
            procedure_date=date(2026, 8, 2),
            clinician_note="Follow up after treatment.",
            status=MedicalCase.Status.TRANSFERRED,
        )
        CaseCollaborationRequest.objects.create(
            medical_case=unrelated_case,
            status=CaseCollaborationRequest.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.origin)

        response = self.client.get(
            reverse("collaboration-request-list"),
            {"status": "COMPLETED"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [visible_request.id],
        )

    def test_dashboard_includes_origin_hospital_cases(self):
        self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
        )
        accepted = self.create_request(
            self.sato,
            CaseCollaborationRequest.Status.ACCEPTED,
            accepted_at=timezone.now(),
        )
        self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.origin)

        response = self.client.get(reverse("hospital-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["today_summary"],
            {
                "new_request_count": 1,
                "in_review_count": 1,
                "completed_count": 1,
            },
        )
        self.assertEqual(
            [item["id"] for item in response.data["ongoing_collaborations"]],
            [accepted.id],
        )

    def test_case_lookup_searches_patient_name_and_case_number(self):
        request_item = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
        )
        self.create_request(
            self.sato,
            CaseCollaborationRequest.Status.REQUESTED,
        )

        name_response = self.client.get(
            reverse("collaboration-request-list"),
            {"search": "Anna"},
        )
        self.assertEqual(len(name_response.data), 1)
        self.assertEqual(name_response.data[0]["id"], request_item.id)

        case_number = (
            f"CASE-{request_item.medical_case.created_at.year}-"
            f"{request_item.medical_case_id:06d}"
        )
        number_response = self.client.get(
            reverse("collaboration-request-list"),
            {"search": case_number},
        )
        self.assertEqual(len(number_response.data), 1)
        self.assertEqual(
            number_response.data[0]["case_number"],
            case_number,
        )

    def test_dashboard_counts_today_and_lists_all_ongoing_cases(self):
        old_time = timezone.now() - timedelta(days=3)
        self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
        )
        old_ongoing = self.create_request(
            self.sato,
            CaseCollaborationRequest.Status.ACCEPTED,
            requested_at=old_time,
            accepted_at=old_time,
        )
        today_ongoing = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.ACCEPTED,
            accepted_at=timezone.now(),
        )
        self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.COMPLETED,
            requested_at=old_time,
            completed_at=timezone.now(),
        )
        self.create_request(
            self.sato,
            CaseCollaborationRequest.Status.COMPLETED,
            requested_at=old_time,
            completed_at=old_time,
        )

        response = self.client.get(reverse("hospital-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["today_summary"],
            {
                "new_request_count": 1,
                "in_review_count": 1,
                "completed_count": 1,
            },
        )
        self.assertSetEqual(
            {
                item["id"]
                for item in response.data["ongoing_collaborations"]
            },
            {old_ongoing.id, today_ongoing.id},
        )

    def test_dashboard_counts_total_unread_messages(self):
        ongoing = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.ACCEPTED,
            accepted_at=timezone.now(),
        )
        chat_room = CaseChatRoom.objects.create(
            medical_case=ongoing.medical_case,
            partner_hospital=self.hospital,
        )
        read_message = CaseChatMessage.objects.create(
            chat_room=chat_room,
            sender=self.origin,
            source_language="ko",
            content="읽은 메시지",
        )
        CaseChatMessage.objects.create(
            chat_room=chat_room,
            sender=self.hospital,
            source_language="ko",
            content="내가 보낸 메시지",
        )
        CaseChatMessage.objects.create(
            chat_room=chat_room,
            sender=self.origin,
            source_language="ko",
            content="안 읽은 메시지",
        )
        CaseChatReadState.objects.create(
            chat_room=chat_room,
            hospital=self.hospital,
            last_read_message=read_message,
        )

        response = self.client.get(reverse("hospital-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_unread_count"], 1)

    def test_collaboration_detail_is_visible_to_both_hospitals(self):
        collaboration_request = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
        )
        url = reverse(
            "collaboration-request-detail",
            kwargs={
                "collaboration_request_id": collaboration_request.id,
            },
        )

        for hospital in (self.origin, self.hospital):
            with self.subTest(hospital=hospital.username):
                self.client.force_authenticate(user=hospital)
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_collaboration_detail_has_header_display_fields(self):
        requested_at = timezone.now() - timedelta(minutes=30)
        collaboration_request = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
            requested_at=requested_at,
        )

        response = self.client.get(
            reverse(
                "collaboration-request-detail",
                kwargs={
                    "collaboration_request_id": (
                        collaboration_request.id
                    ),
                },
            )
        )


        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["patient_name"], "Anna Kim")
        self.assertEqual(response.data["procedure_name"], "Botox")
        self.assertEqual(response.data["procedure_area"], "Forehead")
        self.assertEqual(
            response.data["consultation_title"],
            "Forehead Botox 상담",
        )
        self.assertEqual(
            response.data["procedure_hospital_name"],
            "Seoul Beauty Clinic",
        )
        self.assertEqual(
            response.data["requested_at"],
            requested_at.isoformat().replace("+00:00", "Z"),
        )

        self.assertIn("patient_provided_data", response.data)
        self.assertIn("ai_translation_summary", response.data)
        self.assertEqual(
            response.data["patient_provided_data"],
            {},
        )
        self.assertEqual(
            response.data["ai_translation_summary"], 
            collaboration_request.medical_case.ai_summary,
        )

    def test_collaboration_detail_is_hidden_from_unrelated_hospital(self):
        collaboration_request = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
        )
        self.client.force_authenticate(user=self.other_hospital)

        response = self.client.get(
            reverse(
                "collaboration-request-detail",
                kwargs={
                    "collaboration_request_id": collaboration_request.id,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_read_collaboration_detail(self):
        collaboration_request = self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.REQUESTED,
        )
        self.client.force_authenticate(user=self.anna)

        response = self.client.get(
            reverse(
                "collaboration-request-detail",
                kwargs={
                    "collaboration_request_id": collaboration_request.id,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CaseChatRoomListAndReadTests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="chat-list-patient",
            password="TestPassword!2026",
            name="Anna Kim",
            user_type=User.UserType.PATIENT,
        )
        self.origin = User.objects.create_user(
            username="chat-list-origin",
            password="TestPassword!2026",
            name="Seoul Beauty Clinic",
            user_type=User.UserType.HOSPITAL,
            preferred_language="ko",
        )
        self.partner = User.objects.create_user(
            username="chat-list-partner",
            password="TestPassword!2026",
            name="Tokyo Medical",
            user_type=User.UserType.HOSPITAL,
            preferred_language="ja",
        )
        self.outsider = User.objects.create_user(
            username="chat-list-outsider",
            password="TestPassword!2026",
            name="Outside Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.medical_case = MedicalCase.objects.create(
            patient=self.patient,
            origin_hospital=self.origin,
            partner_hospital=self.partner,
            procedure_name="Botox",
            procedure_area="Forehead",
            procedure_date=date(2026, 8, 1),
            clinician_note="Observe symptoms.",
            status=MedicalCase.Status.TRANSFERRED,
        )
        self.collaboration_request = (
            CaseCollaborationRequest.objects.create(
                medical_case=self.medical_case,
                status=CaseCollaborationRequest.Status.ACCEPTED,
                accepted_at=timezone.now(),
            )
        )
        self.chat_room = CaseChatRoom.objects.create(
            medical_case=self.medical_case,
            partner_hospital=self.partner,
        )
        self.first_message = CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.origin,
            source_language="ko",
            content="첫 번째 메시지",
        )
        CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.partner,
            source_language="ja",
            content="返信です",
        )
        self.latest_message = CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.origin,
            source_language="ko",
            content="최근 원문 메시지",
        )
        CaseChatMessageTranslation.objects.create(
            message=self.latest_message,
            target_language="ja",
            translated_content="最新の翻訳メッセージ",
            status=CaseChatMessageTranslation.Status.COMPLETED,
        )
        self.messages_url = reverse(
            "case-chat-message-list-create",
            kwargs={
                "case_id": self.medical_case.id,
                "room_id": self.chat_room.id,
            },
        )
        self.client.force_authenticate(user=self.partner)

    def test_chat_list_contains_case_latest_message_and_unread_count(self):
        response = self.client.get(reverse("case-chat-room-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        room = response.data[0]
        self.assertEqual(room["patient_name"], "Anna Kim")
        self.assertEqual(room["procedure_name"], "Botox")
        self.assertEqual(room["counterpart_hospital_name"], "Seoul Beauty Clinic")
        self.assertEqual(room["unread_count"], 2)
        self.assertEqual(room["last_message"]["id"], self.latest_message.id)
        self.assertEqual(
            room["last_message"]["content"],
            "최근 원문 메시지",
        )
        self.assertEqual(
            room["last_message"]["translated_content"],
            "最新の翻訳メッセージ",
        )
        self.assertEqual(
            room["last_message"]["display_content"],
            "最新の翻訳メッセージ",
        )
        self.assertIsNotNone(room["last_message_at"])
        self.assertIsNone(room["agreement_id"])
        self.assertIsNone(room["agreement_status"])
        self.assertIsNone(room["agreement_finalized_at"])
        self.assertEqual(room["chat_status"], "IN_REVIEW")
        self.assertEqual(room["chat_status_label"], "검토중")
        self.assertFalse(room["can_view_agreement"])

    def test_chat_list_hides_agreement_until_it_is_final(self):
        agreement = CaseAgreement.objects.create(
            chat_room=self.chat_room,
            judgment_draft="AI 합의안 초안",
            evidence_items=[],
            status=CaseAgreement.Status.AI_DRAFT,
        )

        response = self.client.get(reverse("case-chat-room-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        room = response.data[0]
        self.assertIsNone(room["agreement_id"])
        self.assertIsNone(room["agreement_status"])
        self.assertIsNone(room["agreement_finalized_at"])
        self.assertEqual(room["chat_status"], "IN_REVIEW")
        self.assertFalse(room["can_view_agreement"])

        agreement.status = CaseAgreement.Status.IN_REVIEW
        agreement.save(update_fields=["status", "updated_at"])

        response = self.client.get(reverse("case-chat-room-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        room = response.data[0]
        self.assertIsNone(room["agreement_id"])
        self.assertIsNone(room["agreement_status"])
        self.assertIsNone(room["agreement_finalized_at"])
        self.assertEqual(room["chat_status"], "IN_REVIEW")
        self.assertFalse(room["can_view_agreement"])

    def test_chat_list_completed_status_and_filter_follow_final_agreement(self):
        finalized_at = timezone.now()
        CaseAgreement.objects.create(
            chat_room=self.chat_room,
            judgment_draft="최종 합의 내용",
            evidence_items=[],
            status=CaseAgreement.Status.FINAL,
            finalized_at=finalized_at,
        )

        completed = self.client.get(
            reverse("case-chat-room-list"),
            {"status": "COMPLETED"},
        )
        in_review = self.client.get(
            reverse("case-chat-room-list"),
            {"status": "IN_REVIEW"},
        )

        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(completed.data), 1)
        self.assertEqual(completed.data[0]["chat_status"], "COMPLETED")
        self.assertEqual(completed.data[0]["chat_status_label"], "완료")
        self.assertEqual(
            completed.data[0]["agreement_status"],
            CaseAgreement.Status.FINAL,
        )
        self.assertEqual(
            completed.data[0]["agreement_finalized_at"],
            finalized_at.isoformat().replace("+00:00", "Z"),
        )
        self.assertTrue(completed.data[0]["can_view_agreement"])
        self.assertEqual(in_review.status_code, status.HTTP_200_OK)
        self.assertEqual(in_review.data, [])

    def test_chat_list_rejects_unknown_status_filter(self):
        response = self.client.get(
            reverse("case-chat-room-list"),
            {"status": "UNKNOWN"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {
                "status": (
                    "status는 IN_REVIEW 또는 COMPLETED여야 합니다."
                )
            },
        )

    def test_mark_read_clears_unread_and_new_message_increments_it(self):
        response = self.client.post(
            reverse(
                "case-chat-room-read",
                kwargs={"room_id": self.chat_room.id},
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["last_read_message_id"],
            self.latest_message.id,
        )
        self.assertEqual(response.data["unread_count"], 0)
        self.assertTrue(
            CaseChatReadState.objects.filter(
                chat_room=self.chat_room,
                hospital=self.partner,
                last_read_message=self.latest_message,
            ).exists()
        )

        CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.origin,
            source_language="ko",
            content="새 메시지",
        )
        list_response = self.client.get(reverse("case-chat-room-list"))
        self.assertEqual(list_response.data[0]["unread_count"], 1)

    def test_outside_hospital_cannot_mark_room_as_read(self):
        self.client.force_authenticate(user=self.outsider)

        response = self.client.post(
            reverse(
                "case-chat-room-read",
                kwargs={"room_id": self.chat_room.id},
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_message_content_is_required_in_korean(self):
        response = self.client.post(
            self.messages_url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {"content": ["메시지 내용을 입력해 주세요."]},
        )

    def test_blank_message_content_is_rejected_in_korean(self):
        response = self.client.post(
            self.messages_url,
            {"content": "   "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {"content": ["메시지 내용을 입력해 주세요."]},
        )

    def test_message_content_length_error_is_in_korean(self):
        response = self.client.post(
            self.messages_url,
            {"content": "가" * 4001},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {
                "content": [
                    "메시지는 4,000자 이하로 입력해 주세요."
                ]
            },
        )


class CaseAgreementAPITests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="agreement-patient",
            password="TestPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        self.origin = User.objects.create_user(
            username="agreement-origin",
            password="TestPassword!2026",
            name="Origin Hospital",
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
            name="Outside Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.medical_case = MedicalCase.objects.create(
            patient=self.patient,
            origin_hospital=self.origin,
            partner_hospital=self.partner,
            procedure_name="Laser",
            procedure_area="Face",
            procedure_date=date(2026, 8, 1),
            clinician_note="Observe symptoms.",
            status=MedicalCase.Status.TRANSFERRED,
        )
        self.chat_room = CaseChatRoom.objects.create(
            medical_case=self.medical_case,
            partner_hospital=self.partner,
        )
        url_kwargs = {
            "case_id": self.medical_case.id,
            "room_id": self.chat_room.id,
        }
        self.detail_url = reverse(
            "case-agreement-detail",
            kwargs=url_kwargs,
        )
        self.generate_url = reverse(
            "case-agreement-generate",
            kwargs=url_kwargs,
        )
        self.review_url = reverse(
            "case-agreement-review",
            kwargs=url_kwargs,
        )
        self.payload = {
            "judgment_draft": "경과 관찰이 필요합니다.",
            "evidence_items": [
                {
                    "id": "evidence-1",
                    "content": "감염 징후가 없습니다.",
                    "order": 1,
                }
            ],
        }

    def create_agreement(self):
        self.client.force_authenticate(user=self.origin)
        return self.client.post(
            self.detail_url,
            self.payload,
            format="json",
        )

    def test_agreement_contains_only_three_content_fields(self):
        response = self.create_agreement()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["additional_opinion"], "")
        self.assertEqual(
            response.data["evidence_items"],
            [
                {
                    "id": "evidence-1",
                    "content": "감염 징후가 없습니다.",
                    "order": 1,
                }
            ],
        )
        self.assertNotIn("follow_up_actions", response.data)
        self.assertNotIn("precautions", response.data)
        self.assertNotIn("patient_message", response.data)

    def test_edit_tracks_changed_fields_and_latest_editor(self):
        self.create_agreement()

        response = self.client.patch(
            self.detail_url,
            {
                "judgment_draft": "추가 관찰이 필요합니다.",
                "additional_opinion": "일주일 후 확인을 권장합니다.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["changed_fields"],
            ["judgment_draft", "additional_opinion"],
        )
        self.assertEqual(
            response.data["latest_edit"]["hospital_name"],
            self.origin.name,
        )

    def test_unchanged_patch_does_not_increment_version(self):
        self.create_agreement()

        response = self.client.patch(
            self.detail_url,
            {"judgment_draft": self.payload["judgment_draft"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["changed_fields"], [])
        self.assertEqual(response.data["version"], 1)

    @patch("cases.views.generate_case_agreement")
    def test_ai_does_not_write_additional_opinion(self, generate):
        CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.origin,
            source_language="ko",
            content="감염 징후가 없습니다.",
        )
        generate.return_value = {
            "judgment_draft": "경과 관찰이 필요합니다.",
            "evidence_items": [],
            "additional_opinion": "AI가 작성하면 안 되는 소견",
        }
        self.client.force_authenticate(user=self.origin)

        response = self.client.post(self.generate_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["additional_opinion"], "")

    def test_generate_requires_chat_message(self):
        self.client.force_authenticate(user=self.origin)

        response = self.client.post(self.generate_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {
                "detail": (
                    "합의안을 생성할 채팅 메시지가 없습니다."
                )
            },
        )

    def test_generate_rejects_existing_agreement(self):
        self.create_agreement()

        response = self.client.post(self.generate_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {"detail": "이미 생성된 협진 합의안이 있습니다."},
        )

    @patch("cases.views.generate_case_agreement")
    def test_generate_returns_bad_gateway_when_ai_fails(self, generate):
        CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.origin,
            source_language="ko",
            content="감염 징후가 없습니다.",
        )
        generate.side_effect = RuntimeError("OpenAI unavailable")
        self.client.force_authenticate(user=self.origin)

        response = self.client.post(self.generate_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.data,
            {"detail": "AI 합의안 초안을 생성하지 못했습니다."},
        )

    @patch("cases.views.generate_case_agreement")
    def test_generate_returns_bad_gateway_for_invalid_ai_data(
        self,
        generate,
    ):
        CaseChatMessage.objects.create(
            chat_room=self.chat_room,
            sender=self.origin,
            source_language="ko",
            content="감염 징후가 없습니다.",
        )
        generate.return_value = {
            "judgment_draft": "경과 관찰이 필요합니다.",
            "evidence_items": [{"id": "evidence-1", "order": 1}],
        }
        self.client.force_authenticate(user=self.origin)

        response = self.client.post(self.generate_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.data,
            {"detail": "AI 합의안 초안을 생성하지 못했습니다."},
        )

    def test_second_hospital_review_finalizes_immediately(self):
        self.create_agreement()
        first_response = self.client.post(self.review_url, format="json")
        self.assertEqual(
            first_response.data["status"],
            CaseAgreement.Status.IN_REVIEW,
        )
        self.assertTrue(first_response.data["my_review_completed"])
        self.assertFalse(
            first_response.data["counterpart_review_completed"]
        )
        self.assertFalse(first_response.data["all_reviews_completed"])
        self.assertFalse(first_response.data["can_finalize"])
        self.assertEqual(
            first_response.data["primary_action"],
            {
                "code": "WAITING_FOR_COUNTERPART",
                "label": "상대 검토 대기",
                "enabled": False,
            },
        )

        self.client.force_authenticate(user=self.partner)
        before_second_review = self.client.get(self.detail_url)
        self.assertTrue(before_second_review.data["can_finalize"])
        self.assertEqual(
            before_second_review.data["primary_action"],
            {
                "code": "FINALIZE",
                "label": "최종 합의 완료",
                "enabled": True,
            },
        )

        second_response = self.client.post(self.review_url, format="json")

        self.assertEqual(
            second_response.data["status"],
            CaseAgreement.Status.FINAL,
        )
        self.assertTrue(second_response.data["all_reviews_completed"])
        self.assertFalse(second_response.data["can_finalize"])
        self.assertEqual(
            second_response.data["primary_action"],
            {
                "code": "VIEW_FINAL",
                "label": "최종 합의안 보기",
                "enabled": True,
            },
        )

    def test_explicit_finalize_endpoint_is_not_exposed(self):
        self.create_agreement()
        response = self.client.post(
            f"{self.detail_url}finalize/",
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_first_completion_remains_valid_after_both_hospitals_edit(self):
        self.create_agreement()

        first_review = self.client.post(self.review_url, format="json")
        self.assertEqual(
            first_review.data["status"],
            CaseAgreement.Status.IN_REVIEW,
        )

        first_edit = self.client.patch(
            self.detail_url,
            {"judgment_draft": "첫 번째 병원의 추가 수정"},
            format="json",
        )
        self.assertFalse(first_edit.data["requires_re_review"])
        self.assertTrue(first_edit.data["reviews"][0]["is_current_version"])

        self.client.force_authenticate(user=self.partner)
        second_edit = self.client.patch(
            self.detail_url,
            {"additional_opinion": "두 번째 병원의 최종 수정"},
            format="json",
        )
        self.assertFalse(second_edit.data["requires_re_review"])
        self.assertEqual(len(second_edit.data["reviews"]), 1)
        self.assertTrue(second_edit.data["reviews"][0]["is_current_version"])

        final_response = self.client.post(self.review_url, format="json")
        self.assertEqual(
            final_response.data["status"],
            CaseAgreement.Status.FINAL,
        )
        self.assertFalse(final_response.data["can_edit"])

    def test_final_agreement_cannot_be_edited_or_reopened(self):
        self.create_agreement()
        self.client.post(self.review_url, format="json")
        self.client.force_authenticate(user=self.partner)
        self.client.post(self.review_url, format="json")

        blocked = self.client.patch(
            self.detail_url,
            {"judgment_draft": "수정 내용"},
            format="json",
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            blocked.data,
            {
                "detail": (
                    "최종 합의가 완료된 후에는 "
                    "수정할 수 없습니다."
                )
            },
        )

        reopen_response = self.client.post(
            f"{self.detail_url}revision-request/",
            format="json",
        )
        self.assertEqual(
            reopen_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_outside_hospital_cannot_read_agreement(self):
        self.create_agreement()
        self.client.force_authenticate(user=self.outsider)

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CaseTransferFlowTests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="transfer-patient",
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
            username="transfer-origin",
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
            username="transfer-partner",
            password="TestPassword!2026",
            name="Partner Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.partner_profile = HospitalProfile.objects.create(
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
        self.match_request = HospitalMatchRequest.objects.create(
            symptom_case=self.symptom_case,
            patient=self.patient_profile,
            required_specialty="리프팅",
            search_country="JP",
            search_latitude="35.6762000",
            search_longitude="139.6503000",
            status=HospitalMatchRequest.Status.SELECTED,
            personal_information_provision_agreed=True,
            information_items_purpose_confirmed=True,
            medical_consultation_use_agreed=True,
            withdrawal_right_confirmed=True,
            agreed_at=timezone.now(),
        )
        self.recommendation = HospitalRecommendation.objects.create(
            match_request=self.match_request,
            hospital=self.partner_profile,
            batch_number=1,
            rank_number=1,
            specialty_score=100,
            distance_score=90,
            collaboration_score=20,
            total_score=70,
            distance_km=3,
            is_selected=True,
        )
        self.client.force_authenticate(user=self.patient)

    def transfer_payload(self):
        return {
            "symptom_case_id": self.symptom_case.pk,
            "recommendation_id": self.recommendation.pk,
            "patient_name": "Patient",
            "patient_gender": CaseTransfer.Gender.OTHER,
            "patient_birth_date": "1995-03-10",
        }

    def document_result(self):
        return {
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

    def create_transfer(self):
        with (
            patch(
                "cases.views.analyze_diagnosis_document",
                return_value=self.document_result(),
            ),
            patch(
                "cases.views.generate_patient_symptom_translation_summary",
                return_value="額の腫れと痛みが報告されています。",
            ),
        ):
            return self.client.post(
                reverse("case-transfer-list-create"),
                self.transfer_payload(),
                format="json",
            )

    def test_transfer_is_created_from_selected_recommendation(self):
        response = self.create_transfer()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = CaseTransfer.objects.get(pk=response.data["id"])
        self.assertEqual(transfer.recommendation, self.recommendation)
        self.assertEqual(transfer.partner_hospital, self.partner)
        self.assertEqual(
            transfer.status,
            CaseTransfer.Status.REVIEW_REQUIRED,
        )
        self.assertTrue(
            DiagnosisAnalysis.objects.filter(
                symptom_case=self.symptom_case,
            ).exists()
        )

    def test_transfer_allows_missing_gender_and_birth_date(self):
        payload = self.transfer_payload()
        payload.pop("patient_gender")
        payload.pop("patient_birth_date")

        with (
            patch(
                "cases.views.analyze_diagnosis_document",
                return_value=self.document_result(),
            ),
            patch(
                "cases.views.generate_patient_symptom_translation_summary",
                return_value="Translated summary",
            ),
        ):
            response = self.client.post(
                reverse("case-transfer-list-create"),
                payload,
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = CaseTransfer.objects.get(pk=response.data["id"])
        self.assertIsNone(transfer.patient_gender)
        self.assertIsNone(transfer.patient_birth_date)
        self.assertIsNone(
            transfer.structured_data["patient_info"]["gender"]
        )
        self.assertIsNone(
            transfer.structured_data["patient_info"]["birth_date"]
        )

    def test_transfer_allows_null_gender_and_birth_date(self):
        payload = self.transfer_payload()
        payload["patient_gender"] = None
        payload["patient_birth_date"] = None

        with (
            patch(
                "cases.views.analyze_diagnosis_document",
                return_value=self.document_result(),
            ),
            patch(
                "cases.views.generate_patient_symptom_translation_summary",
                return_value="Translated summary",
            ),
        ):
            response = self.client.post(
                reverse("case-transfer-list-create"),
                payload,
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = CaseTransfer.objects.get(pk=response.data["id"])
        self.assertIsNone(transfer.patient_gender)
        self.assertIsNone(transfer.patient_birth_date)

    def test_transfer_preserves_patient_symptoms_when_ai_values_are_empty(self):
        document_result = self.document_result()
        document_result["symptoms"] = {
            "description": None,
            "start_date": None,
            "onset_timing": None,
            "pain_level": None,
            "areas": [],
            "types": [],
        }

        with (
            patch(
                "cases.views.analyze_diagnosis_document",
                return_value=document_result,
            ),
            patch(
                "cases.views.generate_patient_symptom_translation_summary",
                return_value="Translated summary",
            ),
        ):
            response = self.client.post(
                reverse("case-transfer-list-create"),
                self.transfer_payload(),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = CaseTransfer.objects.get(pk=response.data["id"])
        symptoms = transfer.structured_data["symptoms"]
        self.assertEqual(symptoms["description"], "Swelling and pain")
        self.assertEqual(symptoms["start_date"], "2026-08-10")
        self.assertEqual(symptoms["pain_level"], 3)

    def test_unselected_recommendation_is_rejected(self):
        self.recommendation.is_selected = False
        self.recommendation.save(update_fields=["is_selected"])

        response = self.client.post(
            reverse("case-transfer-list-create"),
            self.transfer_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CaseTransfer.objects.exists())

    def test_transfer_requires_diagnosis_document(self):
        self.symptom_case.diagnosis_document = None
        self.symptom_case.save(update_fields=["diagnosis_document"])

        response = self.client.post(
            reverse("case-transfer-list-create"),
            self.transfer_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_transfer_is_rejected(self):
        first_response = self.create_transfer()
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        second_response = self.client.post(
            reverse("case-transfer-list-create"),
            self.transfer_payload(),
            format="json",
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(CaseTransfer.objects.count(), 1)

    def test_patient_transfer_list_returns_ai_analyzed_untransferred_case(self):
        create_response = self.create_transfer()

        response = self.client.get(
            reverse("case-transfer-list-create"),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        item = response.data[0]
        self.assertEqual(item["id"], create_response.data["id"])
        self.assertEqual(item["symptom_case_id"], self.symptom_case.pk)
        self.assertEqual(item["recommendation_id"], self.recommendation.pk)
        self.assertEqual(item["patient_name"], "Patient")
        self.assertEqual(item["partner_hospital_name"], "Partner Hospital")
        self.assertEqual(item["origin_hospital_name"], "Origin Hospital")
        self.assertEqual(item["procedure_name"], "Botox")
        self.assertEqual(item["procedure_area"], "Forehead")
        self.assertEqual(item["procedure_date"], "2026-08-09")
        self.assertEqual(
            item["status"],
            CaseTransfer.Status.REVIEW_REQUIRED,
        )

    def test_ready_to_transfer_case_remains_in_patient_transfer_list(self):
        create_response = self.create_transfer()
        transfer_id = create_response.data["id"]
        self.client.patch(
            reverse(
                "case-transfer-review",
                kwargs={"transfer_id": transfer_id},
            ),
            {
                "procedure_medication_agreed": True,
                "adverse_effect_clinician_note_agreed": True,
                "overseas_ai_processing_agreed": True,
            },
            format="json",
        )

        response = self.client.get(reverse("case-transfer-list-create"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["status"],
            CaseTransfer.Status.READY_TO_TRANSFER,
        )

    def test_transferred_case_is_hidden_from_patient_list_and_detail(self):
        create_response = self.create_transfer()
        transfer_id = create_response.data["id"]
        self.client.patch(
            reverse(
                "case-transfer-review",
                kwargs={"transfer_id": transfer_id},
            ),
            {
                "procedure_medication_agreed": True,
                "adverse_effect_clinician_note_agreed": True,
                "overseas_ai_processing_agreed": True,
            },
            format="json",
        )
        self.client.post(
            reverse(
                "case-transfer-send",
                kwargs={"transfer_id": transfer_id},
            ),
        )

        list_response = self.client.get(
            reverse("case-transfer-list-create")
        )
        detail_response = self.client.get(
            reverse(
                "case-transfer-detail",
                kwargs={"transfer_id": transfer_id},
            )
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data, [])
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_can_read_untransferred_transfer_detail(self):
        create_response = self.create_transfer()

        response = self.client.get(
            reverse(
                "case-transfer-detail",
                kwargs={"transfer_id": create_response.data["id"]},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], create_response.data["id"])
        self.assertEqual(
            response.data["structured_data"]["procedure"]["name"],
            "Botox",
        )
        self.assertEqual(
            response.data["status"],
            CaseTransfer.Status.REVIEW_REQUIRED,
        )

    def test_hospital_cannot_read_patient_transfer_list_or_detail(self):
        create_response = self.create_transfer()
        self.client.force_authenticate(user=self.partner)

        list_response = self.client.get(
            reverse("case-transfer-list-create")
        )
        detail_response = self.client.get(
            reverse(
                "case-transfer-detail",
                kwargs={"transfer_id": create_response.data["id"]},
            )
        )

        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(detail_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_hospital_selection_does_not_create_collaboration_request(self):
        response = self.client.post(
            reverse(
                "recommendation-select",
                kwargs={
                    "recommendation_id": self.recommendation.pk,
                },
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(CaseCollaborationRequest.objects.exists())
        self.match_request.refresh_from_db()
        self.assertFalse(
            self.match_request.personal_information_provision_agreed,
        )
        self.assertIsNone(self.match_request.agreed_at)

    def test_all_three_transfer_consents_are_required(self):
        create_response = self.create_transfer()

        response = self.client.patch(
            reverse(
                "case-transfer-review",
                kwargs={"transfer_id": create_response.data["id"]},
            ),
            {
                "procedure_medication_agreed": True,
                "adverse_effect_clinician_note_agreed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CaseCollaborationRequest.objects.exists())

    def test_four_match_consents_are_required_before_sync(self):
        self.match_request.personal_information_provision_agreed = False
        self.match_request.information_items_purpose_confirmed = False
        self.match_request.medical_consultation_use_agreed = False
        self.match_request.withdrawal_right_confirmed = False
        self.match_request.agreed_at = None
        self.match_request.save()

        response = self.client.post(
            reverse("case-transfer-list-create"),
            self.transfer_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CaseTransfer.objects.exists())

    def test_match_consent_does_not_create_collaboration_request(self):
        self.match_request.personal_information_provision_agreed = False
        self.match_request.information_items_purpose_confirmed = False
        self.match_request.medical_consultation_use_agreed = False
        self.match_request.withdrawal_right_confirmed = False
        self.match_request.agreed_at = None
        self.match_request.save()

        response = self.client.patch(
            reverse(
                "match-request-consent",
                kwargs={
                    "match_request_id": self.match_request.pk,
                },
            ),
            {
                "personal_information_provision_agreed": True,
                "information_items_purpose_confirmed": True,
                "medical_consultation_use_agreed": True,
                "withdrawal_right_confirmed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["agreed_at"])
        self.assertFalse(CaseCollaborationRequest.objects.exists())

    def test_symptom_completes_only_after_final_agreement(self):
        create_response = self.create_transfer()
        transfer_id = create_response.data["id"]
        transfer = CaseTransfer.objects.select_related(
            "medical_case",
        ).get(id=transfer_id)
        expected_case_number = (
            f"CASE-{transfer.medical_case.created_at.year}-"
            f"{transfer.medical_case_id:06d}"
        )
        self.assertEqual(
            create_response.data["case_number"],
            expected_case_number,
        )
        self.assertFalse(CaseCollaborationRequest.objects.exists())
        self.assertIsNone(
            create_response.data["collaboration_request_id"],
        )

        review_response = self.client.patch(
            reverse(
                "case-transfer-review",
                kwargs={"transfer_id": transfer_id},
            ),
            {
                "procedure_medication_agreed": True,
                "adverse_effect_clinician_note_agreed": True,
                "overseas_ai_processing_agreed": True,
            },
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            review_response.data["case_number"],
            expected_case_number,
        )
        self.assertEqual(
            review_response.data["status"],
            CaseTransfer.Status.READY_TO_TRANSFER,
        )
        self.assertFalse(CaseCollaborationRequest.objects.exists())
        self.assertIsNone(
            review_response.data["collaboration_request_id"],
        )

        send_response = self.client.post(
            reverse(
                "case-transfer-send",
                kwargs={"transfer_id": transfer_id},
            ),
        )
        self.assertEqual(send_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            send_response.data["case_number"],
            expected_case_number,
        )
        collaboration_request = CaseCollaborationRequest.objects.get()
        self.assertEqual(
            send_response.data["collaboration_request_id"],
            collaboration_request.id,
        )
        self.assertEqual(
            send_response.data["collaboration_request_status"],
            CaseCollaborationRequest.Status.REQUESTED,
        )
        self.symptom_case.refresh_from_db()
        self.assertEqual(
            self.symptom_case.status,
            PatientSymptomCase.Status.CONNECTION_REQUESTED,
        )

        self.client.force_authenticate(user=self.partner)
        received_list_response = self.client.get(
            reverse("partner-case-transfer-list"),
        )
        self.assertEqual(
            received_list_response.data[0]["case_number"],
            expected_case_number,
        )

        received_detail_response = self.client.get(
            reverse(
                "partner-case-transfer-detail",
                kwargs={"transfer_id": transfer_id},
            ),
        )
        self.assertEqual(
            received_detail_response.data["case_number"],
            expected_case_number,
        )

        collaboration_detail_response = self.client.get(
            reverse(
                "collaboration-request-detail",
                kwargs={
                    "collaboration_request_id": collaboration_request.id,
                },
            ),
        )
        self.assertEqual(
            collaboration_detail_response.data["case_number"],
            expected_case_number,
        )

        accept_response = self.client.post(
            reverse(
                "collaboration-request-accept",
                kwargs={
                    "collaboration_request_id": collaboration_request.id,
                },
            ),
        )

        self.assertEqual(accept_response.status_code, status.HTTP_200_OK)
        collaboration_request.refresh_from_db()
        self.symptom_case.refresh_from_db()
        self.assertEqual(
            self.symptom_case.status,
            PatientSymptomCase.Status.IN_COLLABORATION,
        )
        self.assertEqual(
            collaboration_request.status,
            CaseCollaborationRequest.Status.ACCEPTED,
        )

        chat_room_id = accept_response.data["chat_room_id"]
        agreement_kwargs = {
            "case_id": collaboration_request.medical_case_id,
            "room_id": chat_room_id,
        }
        agreement_response = self.client.post(
            reverse("case-agreement-detail", kwargs=agreement_kwargs),
            {
                "judgment_draft": "경과 관찰이 필요합니다.",
                "evidence_items": [],
                "additional_opinion": "증상 악화 시 내원 바랍니다.",
            },
            format="json",
        )
        self.assertEqual(
            agreement_response.status_code,
            status.HTTP_201_CREATED,
        )

        review_url = reverse(
            "case-agreement-review",
            kwargs=agreement_kwargs,
        )
        first_review = self.client.post(review_url, format="json")
        self.assertEqual(
            first_review.data["status"],
            CaseAgreement.Status.IN_REVIEW,
        )
        self.symptom_case.refresh_from_db()
        self.assertEqual(
            self.symptom_case.status,
            PatientSymptomCase.Status.IN_COLLABORATION,
        )

        self.client.force_authenticate(user=self.origin)
        final_review = self.client.post(review_url, format="json")
        self.assertEqual(
            final_review.data["status"],
            CaseAgreement.Status.FINAL,
        )
        self.assertTrue(final_review.data["all_reviews_completed"])

        collaboration_request.refresh_from_db()
        self.symptom_case.refresh_from_db()
        self.assertEqual(
            collaboration_request.status,
            CaseCollaborationRequest.Status.COMPLETED,
        )
        self.assertIsNotNone(collaboration_request.completed_at)
        self.assertEqual(
            self.symptom_case.status,
            PatientSymptomCase.Status.COMPLETED,
        )

        blocked_edit = self.client.patch(
            reverse("case-agreement-detail", kwargs=agreement_kwargs),
            {"judgment_draft": "최종 합의 후 수정 시도"},
            format="json",
        )
        self.assertEqual(
            blocked_edit.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        collaboration_request.refresh_from_db()
        self.symptom_case.refresh_from_db()
        self.assertEqual(
            collaboration_request.status,
            CaseCollaborationRequest.Status.COMPLETED,
        )
        self.assertIsNotNone(collaboration_request.completed_at)
        self.assertEqual(
            self.symptom_case.status,
            PatientSymptomCase.Status.COMPLETED,
        )
