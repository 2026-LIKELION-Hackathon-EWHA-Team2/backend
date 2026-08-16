from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from cases.models import MedicalCase

from .models import (
    HospitalProfile,
    MedicalSpecialty,
    PatientProfile,
    User,
)
from .specialties import SpecialtyCode


class PatientProfileReadTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="patient-profile-user",
            password="StrongPassword!2026",
            name="Anna Kim",
            user_type=User.UserType.PATIENT,
        )
        self.profile = PatientProfile.objects.create(
            user=self.user,
            passport_number="M12345678",
            birth_date="1992-05-20",
            phone="+81-90-1234-5678",
            address="Tokyo",
        )
        self.url = reverse("accounts:patient-profile")
        self.client.force_authenticate(user=self.user)

    def test_profile_includes_generated_medical_passport_number(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["medical_passport_no"],
            (
                f"MP-{self.user.date_joined.year}-"
                f"{self.profile.patient_id:04d}"
            ),
        )

    def test_last_updated_uses_joined_at_without_cases(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["last_updated"],
            self.user.date_joined.isoformat().replace("+00:00", "Z"),
        )

    def test_last_updated_uses_latest_case_update(self):
        origin_hospital = User.objects.create_user(
            username="origin-hospital",
            password="StrongPassword!2026",
            name="Origin Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        older_case = MedicalCase.objects.create(
            patient=self.user,
            origin_hospital=origin_hospital,
            procedure_name="Botox",
            procedure_area="Forehead",
            procedure_date="2026-08-01",
            clinician_note="Older case",
        )
        latest_case = MedicalCase.objects.create(
            patient=self.user,
            origin_hospital=origin_hospital,
            procedure_name="Filler",
            procedure_area="Lip",
            procedure_date="2026-08-02",
            clinician_note="Latest case",
        )
        older_updated_at = timezone.now() - timedelta(days=2)
        latest_updated_at = timezone.now() - timedelta(days=1)
        MedicalCase.objects.filter(pk=older_case.pk).update(
            updated_at=older_updated_at,
        )
        MedicalCase.objects.filter(pk=latest_case.pk).update(
            updated_at=latest_updated_at,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["last_updated"],
            latest_updated_at.isoformat().replace("+00:00", "Z"),
        )


class PatientSignUpConsentTests(APITestCase):
    def setUp(self):
        self.signup_url = reverse("accounts:patient-signup")
        self.base_payload = {
            "name": "Anna Kim",
            "login_id": "anna-kim",
            "password": "StrongPassword!2026",
            "terms_agreed": True,
            "privacy_agreed": True,
            "overseas_info_agreed": True,
            "address": "Tokyo",
            "phone": "+81-3-1234-5678",
            "birth_date": "1992-05-20",
            "passport_number": "M12345678",
        }

    def test_overseas_transfer_consent_is_required(self):
        response = self.client.post(
            self.signup_url,
            self.base_payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overseas_transfer_agreed", response.data)

    def test_overseas_transfer_consent_must_be_true(self):
        response = self.client.post(
            self.signup_url,
            {
                **self.base_payload,
                "overseas_transfer_agreed": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overseas_transfer_agreed", response.data)

    def test_patient_signup_saves_overseas_transfer_consent(self):
        response = self.client.post(
            self.signup_url,
            {
                **self.base_payload,
                "overseas_transfer_agreed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="anna-kim")
        self.assertTrue(user.overseas_transfer_agreed)


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

    def test_hospital_website_accepts_free_text(self):
        payload = {
            **self.base_payload,
            "website": "Tokyo Medical homepage",
            "specialties": [
                {"specialty_code": SpecialtyCode.ACNE_SCAR},
            ],
        }

        response = self.client.post(
            self.signup_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            HospitalProfile.objects.get().website,
            "Tokyo Medical homepage",
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


class HospitalListSearchTests(APITestCase):
    def setUp(self):
        patient = User.objects.create_user(
            username="hospital-search-patient",
            password="StrongPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        self.client.force_authenticate(user=patient)
        self.url = reverse("accounts:hospital-list")

        tokyo_user = User.objects.create_user(
            username="tokyo-skin",
            password="StrongPassword!2026",
            name="Tokyo Skin Clinic",
            user_type=User.UserType.HOSPITAL,
        )
        self.tokyo_hospital = HospitalProfile.objects.create(
            user=tokyo_user,
            country="JP",
            city="Tokyo",
            address="Shinjuku",
        )
        seoul_user = User.objects.create_user(
            username="seoul-medical",
            password="StrongPassword!2026",
            name="Seoul Medical",
            user_type=User.UserType.HOSPITAL,
        )
        HospitalProfile.objects.create(
            user=seoul_user,
            country="KR",
            city="Seoul",
            address="Gangnam",
        )

    def test_searches_registered_hospitals_by_name(self):
        response = self.client.get(self.url, {"search": "skin"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["hospital_id"],
            self.tokyo_hospital.hospital_id,
        )

    def test_search_does_not_match_city_or_address(self):
        response = self.client.get(self.url, {"search": "Shinjuku"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_blank_search_returns_all_hospitals(self):
        response = self.client.get(self.url, {"search": "   "})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
