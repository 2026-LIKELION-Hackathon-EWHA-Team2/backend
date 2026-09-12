from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import HospitalProfile, PatientProfile, User
from accounts.specialties import SpecialtyCode
from matching.models import HospitalMatchRequest, HospitalRecommendation
from matching.serializers import HospitalMatchRequestSerializer
from matching.services import (
    calculate_distance_km, calculate_total_score, generate_recommendations,
    optional_distance_km,
)
from matching.validation import NumericDataError
from selfsymptoms.models import PatientSymptomCase


class MatchingNumericTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="numeric-patient", user_type="PATIENT")
        self.patient = PatientProfile.objects.create(
            user=self.user, residence_country="JP", latitude=0, longitude=0,
        )
        hospital_user = User.objects.create_user(username="numeric-hospital", user_type="HOSPITAL")
        self.hospital = HospitalProfile.objects.create(
            user=hospital_user, country="JP", city="Tokyo", address="Tokyo",
            latitude=0, longitude=0,
        )
        self.case = PatientSymptomCase.objects.create(patient=self.patient, status="SUBMITTED")
        self.client.force_authenticate(self.user)
        self.payload = {
            "symptom_case": self.case.pk, "location_source": "CUSTOM",
            "search_country": "JP", "search_latitude": 0, "search_longitude": 0,
        }

    def create_request(self):
        return HospitalMatchRequest.objects.create(
            symptom_case=self.case, patient=self.patient, search_country="JP",
            search_latitude=0, search_longitude=0,
        )

    def create_recommendation(self, request):
        return HospitalRecommendation.objects.create(
            match_request=request, hospital=self.hospital,
            batch_number=1, rank_number=1,
            specialty_score=100, distance_score=90, collaboration_score=20,
            total_score=70, distance_km=0,
        )

    def test_custom_coordinate_and_weight_errors_are_400_before_generation(self):
        with patch("matching.views.generate_recommendations") as generate:
            for field, value in [
                ("search_latitude", 91), ("search_longitude", -181),
                ("search_latitude", "NaN"), ("search_longitude", "Infinity"),
                ("search_latitude", "1.12345678"), ("search_longitude", None),
                ("specialty_weight", -1), ("distance_weight", 101),
                ("collaboration_weight", 0.5), ("specialty_weight", True),
            ]:
                response = self.client.post(reverse("match-request-create"), {
                    **self.payload, field: value,
                }, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)
            generate.assert_not_called()
        self.assertFalse(HospitalMatchRequest.objects.exists())

    def test_weight_defaults_zero_sum_and_non_100_sum(self):
        for weights, valid in [
            ({}, True),
            ({"specialty_weight": 100, "distance_weight": 100, "collaboration_weight": 100}, True),
            ({"specialty_weight": 0, "distance_weight": 0, "collaboration_weight": 0}, False),
            ({"specialty_weight": 0, "distance_weight": 0, "collaboration_weight": 1}, True),
        ]:
            serializer = HospitalMatchRequestSerializer(data={**self.payload, **weights})
            self.assertEqual(serializer.is_valid(), valid, serializer.errors)
            if valid:
                instance = serializer.save(patient=self.patient)
                for field in ("specialty_weight", "distance_weight", "collaboration_weight"):
                    self.assertEqual(getattr(instance, field), weights.get(
                        field, HospitalMatchRequest._meta.get_field(field).get_default(),
                    ))
        self.assertEqual(calculate_total_score(100, 50, 0, 100, 100, 100), 50)

    def test_copied_legacy_profile_coordinates_are_validated(self):
        for latitude, longitude, invalid_field in [
            (91, 0, "search_latitude"), (0, 181, "search_longitude"),
            (Decimal("NaN"), 0, "search_latitude"),
        ]:
            patient = SimpleNamespace(
                residence_country="JP", city="", address="",
                latitude=latitude, longitude=longitude,
            )
            serializer = HospitalMatchRequestSerializer(
                data={"symptom_case": self.case.pk, "location_source": "PROFILE"},
                context={"patient": patient},
            )
            self.assertFalse(serializer.is_valid())
            self.assertIn(invalid_field, serializer.errors)

    def test_network_selection_rejects_invalid_patient_coordinate_before_write(self):
        self.patient.latitude = Decimal("91")
        with patch("matching.views.PatientProfile.objects.get", return_value=self.patient):
            response = self.client.post(reverse("network-hospital-select", kwargs={
                "hospital_id": self.hospital.pk,
            }), {"symptom_case_id": self.case.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("latitude", response.data)
        self.assertFalse(HospitalMatchRequest.objects.exists())

    def test_network_selection_allows_missing_hospital_coordinates(self):
        self.hospital.latitude = self.hospital.longitude = None
        self.hospital.save()
        response = self.client.post(reverse("network-hospital-select", kwargs={
            "hospital_id": self.hospital.pk,
        }), {"symptom_case_id": self.case.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(HospitalRecommendation.objects.get().distance_km)

    def test_network_bad_hospital_data_is_server_error(self):
        self.hospital.longitude = 181
        with patch("matching.views._network_hospitals") as hospitals:
            hospitals.return_value.get.return_value = self.hospital
            response = self.client.post(reverse("network-hospital-select", kwargs={
                "hospital_id": self.hospital.pk,
            }), {"symptom_case_id": self.case.pk}, format="json")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(HospitalMatchRequest.objects.exists())

    def test_distance_edge_cases_and_invalid_stored_coordinates(self):
        self.assertEqual(calculate_distance_km(0, 0, 0, 0), 0)
        self.assertAlmostEqual(calculate_distance_km(0, 0, 0, 180), 20015.0868, places=3)
        self.assertAlmostEqual(calculate_distance_km(-90, -180, 90, 180), 20015.0868, places=3)
        for lat, lon in [(None, None), (91, 0), (0, 181), ("NaN", 0)]:
            self.assertIsNone(optional_distance_km(lat, lon, 0, 0))
            with self.assertRaises(NumericDataError):
                calculate_distance_km(lat, lon, 0, 0)

    def test_database_blocks_invalid_requests_and_recommendations(self):
        request = self.create_request()
        recommendation = self.create_recommendation(request)
        for values in [
            {"search_latitude": 91}, {"search_longitude": 181},
            {"specialty_weight": 101},
            {"specialty_weight": 0, "distance_weight": 0, "collaboration_weight": 0},
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                HospitalMatchRequest.objects.filter(pk=request.pk).update(**values)
        for field, value in [
            ("specialty_score", -1), ("distance_score", 101),
            ("collaboration_score", 101), ("total_score", -1),
            ("distance_km", -1), ("rank_number", 0),
            ("batch_number", 0), ("collaboration_count", -1),
        ]:
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    HospitalRecommendation.objects.filter(pk=recommendation.pk).update(**{field: value})

    def test_invalid_internal_results_do_not_replace_existing_recommendations(self):
        request = self.create_request()
        old = self.create_recommendation(request)
        with patch("matching.services.determine_required_specialty", return_value={
            "specialty_name": "Test", "specialty_code": SpecialtyCode.ACNE_SCAR,
        }), patch("matching.services.calculate_total_score", return_value=float("nan")):
            with self.assertRaises(NumericDataError):
                generate_recommendations(request)
        self.assertTrue(HospitalRecommendation.objects.filter(pk=old.pk).exists())
        request.refresh_from_db()
        self.assertEqual(request.status, "PENDING")

    def test_direct_save_rejects_non_finite_and_fractional_rank(self):
        request = self.create_request()
        recommendation = self.create_recommendation(request)
        for field, value in [
            ("total_score", float("nan")), ("distance_km", float("inf")),
            ("rank_number", 1.5), ("collaboration_count", True),
        ]:
            recommendation.refresh_from_db()
            setattr(recommendation, field, value)
            with self.assertRaises(NumericDataError):
                recommendation.save()

    def test_valid_generation_keeps_score_order_and_zero_distance(self):
        request = self.create_request()
        with patch("matching.services.determine_required_specialty", return_value={
            "specialty_name": "Test", "specialty_code": SpecialtyCode.ACNE_SCAR,
        }):
            recommendations = generate_recommendations(request)
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].distance_km, 0)
        self.assertEqual(recommendations[0].total_score, 40)
        self.assertEqual(recommendations[0].rank_number, 1)


class NumericMigrationTests(TransactionTestCase):
    def test_legacy_audit_blocks_invalid_data_without_changing_it(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [("accounts", "0013_remove_hospitalprofile_language_code"),
               ("matching", "0007_alter_hospitalmatchrequest_search_country")]
        try:
            executor.migrate(old)
            apps = executor.loader.project_state(old).apps
            user = apps.get_model("accounts", "User").objects.create(
                username="legacy-coordinate", user_type="PATIENT",
            )
            Patient = apps.get_model("accounts", "PatientProfile")
            patient = Patient.objects.create(user=user, latitude=91, longitude=0)
            audit = import_module("accounts.migrations.0014_audit_numeric_data").audit_numeric_data
            with connection.schema_editor() as editor:
                with self.assertRaisesRegex(RuntimeError, "PatientProfile.*latitude"):
                    audit(apps, editor)
            self.assertEqual(Patient.objects.get(pk=patient.pk).latitude, 91)
            Patient.objects.filter(pk=patient.pk).update(latitude=None, longitude=None)
            with connection.schema_editor() as editor:
                audit(apps, editor)
        finally:
            # Ensure constraints can be restored even when an assertion fails.
            with connection.cursor() as cursor:
                cursor.execute("UPDATE accounts_patientprofile SET latitude=NULL, longitude=NULL")
            MigrationExecutor(connection).migrate(latest)
