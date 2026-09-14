from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import HospitalProfile, PatientProfile, User


class RolePermissionAPITests(APITestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            username="permission-patient",
            password="StrongPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        PatientProfile.objects.create(user=self.patient_user)

        self.hospital_user = User.objects.create_user(
            username="permission-hospital",
            password="StrongPassword!2026",
            name="Hospital",
            user_type=User.UserType.HOSPITAL,
        )
        HospitalProfile.objects.create(
            user=self.hospital_user,
            country="KR",
            city="Seoul",
            address="Seoul",
        )

    def test_hospital_cannot_access_patient_profile(self):
        self.client.force_authenticate(user=self.hospital_user)

        response = self.client.get(reverse("accounts:patient-profile"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_cannot_access_hospital_profile(self):
        self.client.force_authenticate(user=self.patient_user)

        response = self.client.get(reverse("accounts:hospital-profile"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_access_role_protected_api(self):
        response = APIClient().get(reverse("accounts:patient-profile"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
