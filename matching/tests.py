import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from accounts.models import HospitalProfile, MedicalSpecialty, User
from accounts.specialties import SpecialtyCode

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
