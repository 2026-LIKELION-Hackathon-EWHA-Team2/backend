import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    HospitalProfile,
    MedicalSpecialty,
    PatientProfile,
    User,
)
from accounts.specialties import SpecialtyCode
from matching.models import HospitalMatchRequest
from selfsymptoms.models import PatientSymptomCase

from .ai_service import analyze_required_specialty
from .services import calculate_specialty_score


class SpecialtyMatchingScoreTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="matching-hospital",
            password="StrongPassword!2026",
            name="Matching Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        self.hospital = HospitalProfile.objects.create(
            user=user,
            country="JP",
            city="Tokyo",
            address="1-1 Chiyoda",
        )
        MedicalSpecialty.objects.create(
            hospital=self.hospital,
            specialty_code=SpecialtyCode.PIGMENTATION,
            specialty_name="색소",
        )
        MedicalSpecialty.objects.create(
            hospital=self.hospital,
            specialty_code=SpecialtyCode.CUSTOM,
            specialty_name="두피 클리닉",
        )

    def test_standard_specialty_matches_by_code(self):
        score = calculate_specialty_score(
            required_specialty="Pigmentation",
            required_specialty_code=SpecialtyCode.PIGMENTATION,
            hospital=self.hospital,
        )

        self.assertEqual(score, 100)

    def test_custom_specialty_matches_normalized_name(self):
        score = calculate_specialty_score(
            required_specialty="  두피   클리닉 ",
            required_specialty_code=SpecialtyCode.CUSTOM,
            hospital=self.hospital,
        )

        self.assertEqual(score, 100)

    def test_unmatched_specialty_has_zero_score(self):
        score = calculate_specialty_score(
            required_specialty="제모",
            required_specialty_code=SpecialtyCode.HAIR_REMOVAL,
            hospital=self.hospital,
        )

        self.assertEqual(score, 0)

    @patch("matching.ai_service.client.responses.create")
    def test_ai_result_includes_stable_specialty_code(self, create):
        create.return_value.output_text = json.dumps(
            {"required_specialty": "색소"},
            ensure_ascii=False,
        )
        empty_relation = Mock()
        empty_relation.all.return_value = []
        symptom_case = SimpleNamespace(
            areas=empty_relation,
            symptom_types=empty_relation,
            onset_timing=None,
            pain_level=None,
            description="색소 침착",
            symptom_start_date=None,
        )

        result = analyze_required_specialty(symptom_case)

        self.assertEqual(
            result,
            {
                "specialty_code": SpecialtyCode.PIGMENTATION,
                "specialty_name": "색소",
            },
        )


class HospitalMatchRequestStatusTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="matching-patient",
            password="StrongPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        self.patient = PatientProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)
        self.url = reverse("match-request-create")

    def payload(self, symptom_case):
        return {
            "symptom_case": symptom_case.pk,
            "location_source": "CUSTOM",
            "search_country": "JP",
            "search_latitude": "35.6762000",
            "search_longitude": "139.6503000",
        }

    def test_draft_case_cannot_start_matching(self):
        symptom_case = PatientSymptomCase.objects.create(
            patient=self.patient,
            status=PatientSymptomCase.Status.DRAFT,
        )

        response = self.client.post(
            self.url,
            self.payload(symptom_case),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        symptom_case.refresh_from_db()
        self.assertEqual(
            symptom_case.status,
            PatientSymptomCase.Status.DRAFT,
        )

    @patch("matching.views.generate_recommendations")
    def test_ai_failure_restores_submitted_status(self, generate):
        generate.side_effect = RuntimeError("AI unavailable")
        symptom_case = PatientSymptomCase.objects.create(
            patient=self.patient,
            status=PatientSymptomCase.Status.SUBMITTED,
        )

        response = self.client.post(
            self.url,
            self.payload(symptom_case),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        symptom_case.refresh_from_db()
        self.assertEqual(
            symptom_case.status,
            PatientSymptomCase.Status.SUBMITTED,
        )
    @patch("matching.views.generate_recommendations")
    def test_profile_location_is_copied_to_match_request(
        self,
        generate,
    ):
        generate.return_value = []

        self.patient.residence_country = "KR"
        self.patient.city = "Seoul"
        self.patient.address = "Gangnam-gu"
        self.patient.latitude = "37.4979000"
        self.patient.longitude = "127.0276000"
        self.patient.save()

        symptom_case = PatientSymptomCase.objects.create(
            patient=self.patient,
            status=PatientSymptomCase.Status.SUBMITTED,
        )

        response = self.client.post(
            self.url,
            {
                "symptom_case": symptom_case.pk,
                "location_source": "PROFILE",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        match_request = HospitalMatchRequest.objects.get()
        self.assertEqual(match_request.search_country, "KR")
        self.assertEqual(match_request.search_city, "Seoul")
        self.assertEqual(
            str(match_request.search_latitude),
            "37.4979000",
        )