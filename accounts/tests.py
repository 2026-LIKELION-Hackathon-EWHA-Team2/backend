from unittest.mock import patch
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import HospitalProfile, MedicalSpecialty, PatientProfile, User


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

    def test_website_is_saved_as_free_text(self):
        self.payload["website"] = "hospital homepage"

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            HospitalProfile.objects.get().website,
            "hospital homepage",
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


class PatientSignUpTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/accounts/signup/"
        self.payload = {
            "name": "After Lee",
            "login_id": "after123",
            "password": "StrongPassword!123",
            "user_type": User.UserType.PATIENT,
            "address": "Tokyo, Japan",
            "phone": "+81-3-1234-5678",
            "birth_date": "2004-03-17",
            "passport_number": "M12345678",
            "terms_agreed": True,
            "privacy_agreed": True,
            "overseas_info_agreed": True,
            "overseas_transfer_agreed": True,
            "marketing_agreed": False,
            "location_info_agreed": False,
        }

    def test_patient_signup_creates_profile_and_returns_id(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username=self.payload["login_id"])
        profile = PatientProfile.objects.get(user=user)
        self.assertEqual(response.data["patient_profile_id"], profile.patient_id)
        self.assertEqual(profile.address, self.payload["address"])
        self.assertEqual(profile.phone, self.payload["phone"])
        self.assertEqual(profile.passport_number, self.payload["passport_number"])
        self.assertEqual(profile.birth_date.isoformat(), self.payload["birth_date"])

    def test_missing_patient_fields_are_rejected(self):
        for field in ("address", "phone", "birth_date", "passport_number"):
            payload = self.payload.copy()
            payload.pop(field)

            response = self.client.post(self.url, payload, format="json")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn(field, response.data)

    def test_overseas_transfer_agreement_is_required(self):
        self.payload["overseas_transfer_agreed"] = False

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overseas_transfer_agreed", response.data)
        self.assertFalse(User.objects.filter(username="after123").exists())

    def test_optional_agreements_are_saved(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username=self.payload["login_id"])
        self.assertFalse(user.marketing_agreed)
        self.assertFalse(user.location_info_agreed)

    @patch("accounts.serializers.PatientProfile.objects.create")
    def test_user_is_rolled_back_when_profile_creation_fails(self, create):
        create.side_effect = RuntimeError("patient profile creation failed")

        with self.assertRaises(RuntimeError):
            self.client.post(self.url, self.payload, format="json")

        self.assertFalse(User.objects.filter(username="after123").exists())


class HospitalListSearchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        patient_user = User.objects.create_user(
            username="patient",
            password="StrongPassword!123",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        access_token = RefreshToken.for_user(patient_user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        self.url = "/accounts/hospitals/"

        tokyo_user = User.objects.create_user(
            username="tokyo-hospital",
            password="StrongPassword!123",
            name="Tokyo Skin Clinic",
            user_type=User.UserType.HOSPITAL,
        )
        self.tokyo_hospital = HospitalProfile.objects.create(
            user=tokyo_user,
            country="Japan",
            city="Tokyo",
            address="Shibuya 1-2-3",
        )
        MedicalSpecialty.objects.create(
            hospital=self.tokyo_hospital,
            specialty_name="Dermatology",
        )

        seoul_user = User.objects.create_user(
            username="seoul-hospital",
            password="StrongPassword!123",
            name="Seoul Medical Center",
            user_type=User.UserType.HOSPITAL,
        )
        HospitalProfile.objects.create(
            user=seoul_user,
            country="Korea",
            city="Seoul",
            address="Gangnam 4-5-6",
        )

    def test_searches_registered_hospitals_by_name(self):
        response = self.client.get(self.url, {"search": "skin"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["hospital_id"],
            self.tokyo_hospital.hospital_id,
        )

    def test_does_not_search_hospitals_by_specialty(self):
        response = self.client.get(self.url, {"search": "dermatology"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_does_not_search_hospitals_by_location(self):
        response = self.client.get(self.url, {"search": "shibuya"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_returns_all_hospitals_without_search_query(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_requires_authentication(self):
        self.client.credentials()

        response = self.client.get(self.url, {"search": "Tokyo"})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
