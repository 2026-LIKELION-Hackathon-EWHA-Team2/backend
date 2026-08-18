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

    def test_case_lookup_returns_all_received_dates_and_filters_status(self):
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
        ongoing = self.create_request(
            self.sato,
            CaseCollaborationRequest.Status.ACCEPTED,
            requested_at=old_time,
            accepted_at=old_time,
        )
        self.create_request(
            self.anna,
            CaseCollaborationRequest.Status.COMPLETED,
            requested_at=old_time,
            completed_at=timezone.now(),
        )

        response = self.client.get(reverse("hospital-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["today_summary"],
            {
                "received_count": 1,
                "under_review_count": 1,
                "completed_count": 1,
            },
        )
        self.assertEqual(
            [item["id"] for item in response.data["ongoing_collaborations"]],
            [ongoing.id],
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
        self.revision_request_url = reverse(
            "case-agreement-revision-request",
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

    def test_both_hospitals_review_to_finalize(self):
        self.create_agreement()
        first_response = self.client.post(self.review_url, format="json")
        self.assertEqual(
            first_response.data["status"],
            CaseAgreement.Status.IN_REVIEW,
        )

        self.client.force_authenticate(user=self.partner)
        second_response = self.client.post(self.review_url, format="json")

        self.assertEqual(
            second_response.data["status"],
            CaseAgreement.Status.FINAL,
        )

    def test_final_agreement_requires_revision_request(self):
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
                    "최종 합의 내용은 수정 요청 후 "
                    "변경할 수 있습니다."
                )
            },
        )

        reopened = self.client.post(
            self.revision_request_url,
            format="json",
        )
        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(
            reopened.data["status"],
            CaseAgreement.Status.IN_REVIEW,
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

        revision_response = self.client.post(
            reverse(
                "case-agreement-revision-request",
                kwargs=agreement_kwargs,
            ),
            format="json",
        )
        self.assertEqual(
            revision_response.status_code,
            status.HTTP_200_OK,
        )

        collaboration_request.refresh_from_db()
        self.symptom_case.refresh_from_db()
        self.assertEqual(
            collaboration_request.status,
            CaseCollaborationRequest.Status.ACCEPTED,
        )
        self.assertIsNone(collaboration_request.completed_at)
        self.assertEqual(
            self.symptom_case.status,
            PatientSymptomCase.Status.IN_COLLABORATION,
        )
