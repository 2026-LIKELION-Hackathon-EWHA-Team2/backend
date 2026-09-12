from decimal import Decimal

from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import HospitalProfile, PatientProfile, User
from accounts.specialties import SpecialtyCode


class ProfileCoordinateTests(APITestCase):
    def setUp(self):
        self.profiles = []
        for role, model, route in [
            (User.UserType.PATIENT, PatientProfile, "patient-profile"),
            (User.UserType.HOSPITAL, HospitalProfile, "hospital-profile"),
        ]:
            user = User.objects.create_user(username=role, user_type=role)
            extra = {} if role == User.UserType.PATIENT else {
                "country": "JP", "city": "Tokyo", "address": "Tokyo",
            }
            profile = model.objects.create(user=user, **extra)
            self.profiles.append((user, profile, reverse("accounts:" + route)))

    def test_boundaries_negative_and_zero_coordinates(self):
        for user, profile, url in self.profiles:
            self.client.force_authenticate(user)
            for lat, lon in [(-90, -180), (90, 180), (0, 0), (-33.5, -70.5)]:
                response = self.client.patch(url, {
                    "latitude": lat, "longitude": lon,
                }, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                profile.refresh_from_db()
                self.assertEqual(profile.latitude, Decimal(str(lat)))
                self.assertEqual(profile.longitude, Decimal(str(lon)))

    def test_invalid_format_range_and_precision(self):
        for user, profile, url in self.profiles:
            self.client.force_authenticate(user)
            for field, value in [
                ("latitude", 90.0000001), ("latitude", -90.0000001),
                ("longitude", 180.0000001), ("longitude", -180.0000001),
                ("latitude", "NaN"), ("longitude", "Infinity"),
                ("latitude", "-Infinity"), ("latitude", "not-a-number"),
                ("latitude", "1.12345678"), ("latitude", True),
                ("latitude", ""),
            ]:
                with self.subTest(role=user.user_type, field=field, value=value):
                    payload = {"latitude": 0, "longitude": 0, field: value}
                    response = self.client.patch(url, payload, format="json")
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)

    def test_patch_uses_existing_pair_and_requires_both_for_removal(self):
        for user, profile, url in self.profiles:
            self.client.force_authenticate(user)
            response = self.client.patch(url, {"latitude": 0}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn("longitude", response.data)
            self.client.patch(url, {"latitude": 0, "longitude": 0}, format="json")
            response = self.client.patch(url, {"latitude": 1}, format="json")
            self.assertEqual(response.status_code, 200)
            response = self.client.patch(url, {"latitude": None}, format="json")
            self.assertEqual(response.status_code, 400)
            response = self.client.patch(url, {
                "latitude": None, "longitude": None,
            }, format="json")
            self.assertEqual(response.status_code, 200)
            profile.refresh_from_db()
            self.assertIsNone(profile.latitude)
            self.assertIsNone(profile.longitude)

    def test_database_rejects_invalid_pair_and_ranges_without_serializer(self):
        for user, profile, url in self.profiles:
            for values in [
                {"latitude": 0}, {"latitude": 91, "longitude": 0},
                {"latitude": 0, "longitude": 181},
            ]:
                with self.subTest(model=type(profile).__name__, values=values):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        type(profile).objects.filter(pk=profile.pk).update(**values)


class SignupLocationTests(APITestCase):
    def payload(self, role, suffix=""):
        data = {
            "name": "Test User", "login_id": f"signup-{role}-{suffix}",
            "password": "StrongPassword!2026",
            "terms_agreed": True, "privacy_agreed": True,
            "overseas_info_agreed": True, "address": "Tokyo",
            "phone": "123456789",
        }
        if role == "patient":
            data.update(
                overseas_transfer_agreed=True, birth_date="1995-01-01",
                passport_number="P123456", residence_country="Japan",
            )
        else:
            data.update(
                country="USA", city="Boston",
                specialties=[{"specialty_code": SpecialtyCode.ACNE_SCAR}],
            )
        return data

    def test_signup_saves_country_and_coordinates_in_profile(self):
        for role in ("patient", "hospital"):
            data = self.payload(role)
            data.update(latitude=0, longitude=-73.1234567)
            response = self.client.post(
                reverse(f"accounts:{role}-signup"), data, format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            user = User.objects.get(username=data["login_id"])
            profile = getattr(user, f"{role}_profile")
            field = "residence_country" if role == "patient" else "country"
            self.assertEqual(getattr(profile, field), "JP" if role == "patient" else "US")
            self.assertEqual(profile.latitude, 0)
            self.assertEqual(profile.longitude, Decimal("-73.1234567"))

    def test_signup_allows_omitted_coordinate_pair(self):
        for role in ("patient", "hospital"):
            data = self.payload(role)
            response = self.client.post(
                reverse(f"accounts:{role}-signup"), data, format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            profile = getattr(User.objects.get(username=data["login_id"]), f"{role}_profile")
            self.assertIsNone(profile.latitude)
            self.assertIsNone(profile.longitude)

    def test_signup_requires_country_and_rejects_invalid_coordinates_atomically(self):
        for role in ("patient", "hospital"):
            country = "residence_country" if role == "patient" else "country"
            for index, invalid in enumerate([
                {country: None}, {country: ""}, {country: "UNKNOWN"},
                {"latitude": 1}, {"latitude": 91, "longitude": 0},
            ]):
                data = {**self.payload(role, str(index)), **invalid}
                response = self.client.post(
                    reverse(f"accounts:{role}-signup"), data, format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(User.objects.filter(username=data["login_id"]).exists())
            data = self.payload(role, "missing")
            del data[country]
            response = self.client.post(
                reverse(f"accounts:{role}-signup"), data, format="json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn(country, response.data)
