from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import HospitalProfile, PatientProfile, User

from .models import PatientSymptomCase, PatientSymptomImage


class PatientSymptomCaseSubmitAPITests(APITestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            username="symptom-patient",
            password="StrongPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
        )
        hospital_user = User.objects.create_user(
            username="symptom-hospital",
            password="StrongPassword!2026",
            name="Origin Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.hospital = HospitalProfile.objects.create(
            user=hospital_user,
            country="KR",
            city="Seoul",
            address="Seoul",
        )
        self.client.force_authenticate(user=self.patient_user)

    def create_case(self, **overrides):
        values = {
            "patient": self.patient,
            "diagnosed_hospital": self.hospital,
            "diagnosis_document": SimpleUploadedFile(
                "diagnosis.pdf",
                b"diagnosis",
                content_type="application/pdf",
            ),
            "description": "붓기와 통증이 있습니다.",
        }
        values.update(overrides)
        return PatientSymptomCase.objects.create(**values)

    def test_status_is_server_controlled_on_create(self):
        response = self.client.post(
            reverse("symptom-case-list"),
            {
                "diagnosed_hospital": self.hospital.pk,
                "diagnosis_document": SimpleUploadedFile(
                    "diagnosis.pdf",
                    b"diagnosis",
                    content_type="application/pdf",
                ),
                "description": "통증이 있습니다.",
                "status": PatientSymptomCase.Status.COMPLETED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["status"],
            PatientSymptomCase.Status.DRAFT,
        )

    def test_case_can_be_completed_across_registration_steps(self):
        create_response = self.client.post(
            reverse("symptom-case-list"),
            {},
            format="json",
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            create_response.data["status"],
            PatientSymptomCase.Status.DRAFT,
        )
        self.assertIsNone(
            create_response.data["diagnosed_hospital"],
        )
        self.assertIsNone(
            create_response.data["diagnosis_document"],
        )

        symptom_case_id = create_response.data["symptom_case_id"]

        image_response = self.client.post(
            reverse("symptom-image-list"),
            {
                "symptom_case": symptom_case_id,
                "image": SimpleUploadedFile(
                    "symptom.gif",
                    bytes.fromhex(
                        "47494638396101000100800000000000ffffff"
                        "21f90401000000002c000000000100010000"
                        "02024401003b"
                    ),
                    content_type="image/gif",
                ),
                "display_order": 1,
            },
            format="multipart",
        )

        self.assertEqual(
            image_response.status_code,
            status.HTTP_201_CREATED,
        )

        symptom_response = self.client.patch(
            reverse(
                "symptom-case-detail",
                kwargs={"pk": symptom_case_id},
            ),
            {
                "symptom_start_date": "2026-08-16",
                "onset_timing": "IMMEDIATE",
                "description": "붓기와 통증이 있습니다.",
                "pain_level": 3,
                "areas": [
                    {"area_type": "FOREHEAD"},
                ],
                "symptom_types": [
                    {"symptom_type": "SWELLING"},
                    {"symptom_type": "PAIN"},
                ],
            },
            format="json",
        )

        self.assertEqual(
            symptom_response.status_code,
            status.HTTP_200_OK,
        )

        document_response = self.client.patch(
            reverse(
                "symptom-case-detail",
                kwargs={"pk": symptom_case_id},
            ),
            {
                "diagnosed_hospital": self.hospital.pk,
                "diagnosis_document": SimpleUploadedFile(
                    "diagnosis.pdf",
                    b"diagnosis",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )

        self.assertEqual(
            document_response.status_code,
            status.HTTP_200_OK,
        )

        submit_response = self.client.post(
            reverse(
                "symptom-case-submit",
                kwargs={"pk": symptom_case_id},
            ),
        )

        self.assertEqual(
            submit_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            submit_response.data["status"],
            PatientSymptomCase.Status.SUBMITTED,
        )
        self.assertEqual(
            PatientSymptomImage.objects.filter(
                symptom_case_id=symptom_case_id,
            ).count(),
            1,
        )

    def test_empty_draft_cannot_be_submitted(self):
        create_response = self.client.post(
            reverse("symptom-case-list"),
            {},
            format="json",
        )

        symptom_case_id = create_response.data["symptom_case_id"]
        submit_response = self.client.post(
            reverse(
                "symptom-case-submit",
                kwargs={"pk": symptom_case_id},
            ),
        )

        self.assertEqual(
            submit_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("diagnosed_hospital", submit_response.data)
        self.assertIn("diagnosis_document", submit_response.data)
        self.assertIn("symptoms", submit_response.data)

    def test_submit_moves_draft_to_submitted(self):
        symptom_case = self.create_case()

        response = self.client.post(
            reverse(
                "symptom-case-submit",
                kwargs={"pk": symptom_case.pk},
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        symptom_case.refresh_from_db()
        self.assertEqual(
            symptom_case.status,
            PatientSymptomCase.Status.SUBMITTED,
        )

    def test_submit_requires_symptom_content(self):
        symptom_case = self.create_case(description="")

        response = self.client.post(
            reverse(
                "symptom-case-submit",
                kwargs={"pk": symptom_case.pk},
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("symptoms", response.data)
        symptom_case.refresh_from_db()
        self.assertEqual(
            symptom_case.status,
            PatientSymptomCase.Status.DRAFT,
        )

    def test_submitted_case_cannot_be_edited(self):
        symptom_case = self.create_case(
            status=PatientSymptomCase.Status.SUBMITTED,
        )

        response = self.client.patch(
            reverse(
                "symptom-case-detail",
                kwargs={"pk": symptom_case.pk},
            ),
            {"description": "수정된 내용"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
