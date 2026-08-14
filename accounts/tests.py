from unittest.mock import patch
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import HospitalProfile, MedicalSpecialty, User


class HospitalSignUpTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/accounts/signup/"
        self.payload = {
            "name": "Seoul Medical Center",
            "login_id": "seoul-medical",
            "password": "StrongPassword!123",
            "user_type": User.UserType.HOSPITAL,
            "terms_agreed": True,
            "privacy_agreed": True,
            "overseas_info_agreed": True,
            "location_info_agreed": True,
            "marketing_agreed": True,
            "preferred_language": User.Language.ENGLISH,
            "country": "KR",
            "city": "Seoul",
            "address": "123 Teheran-ro",
            "latitude": "37.4999000",
            "longitude": "127.0364000",
            "phone": "+82-2-1234-5678",
            "website": "https://hospital.example.com",
            "medical_specialty": "Dermatology",
        }

    def test_hospital_signup_creates_profile_and_returns_id(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username=self.payload["login_id"])
        profile = HospitalProfile.objects.get(user=user)
        self.assertEqual(response.data["hospital_profile_id"], profile.hospital_id)
        self.assertEqual(profile.country, self.payload["country"])
        self.assertEqual(profile.latitude, Decimal(self.payload["latitude"]))

    def test_hospital_signup_creates_specialties(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            MedicalSpecialty.objects.get().specialty_name,
            self.payload["medical_specialty"],
        )

    def test_required_agreement_is_rejected(self):
        self.payload["location_info_agreed"] = False

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("location_info_agreed", response.data)
        self.assertFalse(User.objects.filter(username="seoul-medical").exists())

    def test_missing_hospital_fields_are_rejected(self):
        for field in (
            "country",
            "city",
            "address",
            "latitude",
            "longitude",
            "medical_specialty",
        ):
            payload = self.payload.copy()
            payload.pop(field)

            response = self.client.post(self.url, payload, format="json")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn(field, response.data)

    def test_optional_agreements_are_saved(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username=self.payload["login_id"])
        self.assertTrue(user.marketing_agreed)
        self.assertTrue(user.location_info_agreed)

    @patch("accounts.serializers.MedicalSpecialty.objects.create")
    def test_user_is_rolled_back_when_profile_creation_fails(self, create):
        create.side_effect = RuntimeError("specialty creation failed")

        with self.assertRaises(RuntimeError):
            self.client.post(self.url, self.payload, format="json")

        self.assertFalse(User.objects.filter(username="seoul-medical").exists())
        self.assertFalse(HospitalProfile.objects.exists())
