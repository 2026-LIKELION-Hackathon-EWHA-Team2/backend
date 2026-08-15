from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import MedicalSpecialty, User
from .specialties import SpecialtyCode


class HospitalSignUpSpecialtyTests(APITestCase):
    def setUp(self):
        self.signup_url = reverse("accounts:hospital-signup")
        self.options_url = reverse(
            "accounts:medical-specialty-options"
        )
        self.base_payload = {
            "name": "Tokyo Medical",
            "login_id": "tokyo-medical",
            "password": "StrongPassword!2026",
            "terms_agreed": True,
            "privacy_agreed": True,
            "overseas_info_agreed": True,
            "country": "JP",
            "city": "Tokyo",
            "address": "1-1 Chiyoda",
            "phone": "+81-3-1234-5678",
            "website": "https://example.com",
        }

    def test_specialty_options_include_signup_choices(self):
        response = self.client.get(self.options_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        options = {
            item["specialty_code"]: item
            for item in response.data["specialties"]
        }

        self.assertEqual(
            options[SpecialtyCode.ACNE_SCAR]["specialty_name"],
            "여드름·흉터",
        )
        self.assertEqual(
            options[SpecialtyCode.BOTOX_FILLER]["specialty_name"],
            "보톡스·필러",
        )
        self.assertTrue(
            options[SpecialtyCode.CUSTOM]["requires_custom_name"]
        )

    def test_hospital_can_sign_up_with_multiple_specialties(self):
        payload = {
            **self.base_payload,
            "specialties": [
                {"specialty_code": SpecialtyCode.ACNE_SCAR},
                {"specialty_code": SpecialtyCode.PIGMENTATION},
                {
                    "specialty_code": SpecialtyCode.CUSTOM,
                    "specialty_name": "두피",
                },
            ],
        }

        response = self.client.post(
            self.signup_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="tokyo-medical")
        specialties = list(
            user.hospital_profile.specialties.order_by(
                "hospital_specialty_id"
            ).values_list("specialty_code", "specialty_name")
        )
        self.assertEqual(
            specialties,
            [
                (SpecialtyCode.ACNE_SCAR, "여드름·흉터"),
                (SpecialtyCode.PIGMENTATION, "색소"),
                (SpecialtyCode.CUSTOM, "두피"),
            ],
        )

    def test_duplicate_specialties_are_rejected(self):
        payload = {
            **self.base_payload,
            "specialties": [
                {"specialty_code": SpecialtyCode.PIGMENTATION},
                {"specialty_code": SpecialtyCode.PIGMENTATION},
            ],
        }

        response = self.client.post(
            self.signup_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("specialties", response.data)
        self.assertFalse(
            MedicalSpecialty.objects.filter(
                specialty_code=SpecialtyCode.PIGMENTATION
            ).exists()
        )

    def test_custom_specialty_requires_a_name(self):
        payload = {
            **self.base_payload,
            "specialties": [
                {"specialty_code": SpecialtyCode.CUSTOM},
            ],
        }

        response = self.client.post(
            self.signup_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("specialties", response.data)

    def test_legacy_single_specialty_name_is_supported(self):
        payload = {
            **self.base_payload,
            "specialty_name": "여드름.흉터",
        }

        response = self.client.post(
            self.signup_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        specialty = MedicalSpecialty.objects.get()
        self.assertEqual(specialty.specialty_code, SpecialtyCode.ACNE_SCAR)
        self.assertEqual(specialty.specialty_name, "여드름·흉터")
