from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from accounts.models import HospitalProfile, PatientProfile, User
from accounts.specialties import SpecialtyCode


class HospitalLanguageTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="language-hospital",
            name="Language Hospital",
            user_type=User.UserType.HOSPITAL,
            preferred_language="ja",
        )
        self.profile = HospitalProfile.objects.create(
            user=self.user, country="JP", city="Tokyo", address="Tokyo",
        )
        self.url = reverse("accounts:hospital-profile")
        self.client.force_authenticate(self.user)
        patient = User.objects.create_user(
            username="language-patient", user_type=User.UserType.PATIENT,
        )
        PatientProfile.objects.create(user=patient)
        self.patient_client = APIClient()
        self.patient_client.force_authenticate(patient)

    def test_read_uses_account_language_for_both_names(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["preferred_language"], "ja")
        self.assertEqual(response.data["language_code"], "ja")

    def test_both_input_names_update_the_same_account_field(self):
        for field, language in [
            ("preferred_language", "zh"), ("language_code", "en"),
            ("preferred_language", "ko"), ("language_code", "ja"),
        ]:
            with self.subTest(field=field, language=language):
                response = self.client.patch(
                    self.url, {field: language}, format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.assertEqual(self.user.preferred_language, language)
                self.assertEqual(response.data["preferred_language"], language)
                self.assertEqual(response.data["language_code"], language)
                # Network/matching responses must reflect the same saved language.
                detail = self.patient_client.get(reverse(
                    "network-hospital-detail",
                    kwargs={"hospital_id": self.profile.pk},
                ))
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.data["preferred_language"], language)

    def test_matching_aliases_are_accepted(self):
        response = self.client.patch(self.url, {
            "preferred_language": "zh", "language_code": "zh",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, "zh")

    def test_conflicting_aliases_do_not_save_other_profile_changes(self):
        response = self.client.patch(self.url, {
            "preferred_language": "zh", "language_code": "en", "city": "Changed",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("language_code", response.data)
        self.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.profile.city, "Tokyo")
        self.assertEqual(self.user.preferred_language, "ja")

    def test_invalid_language_is_rejected_for_both_names(self):
        for field in ("preferred_language", "language_code"):
            for value in ("fr", "", None):
                with self.subTest(field=field, value=value):
                    response = self.client.patch(
                        self.url, {field: value}, format="json",
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, "ja")

    def test_unrelated_patch_preserves_language(self):
        response = self.client.patch(self.url, {"city": "Osaka"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, "ja")

    def test_signup_language_is_visible_in_profile(self):
        response = self.client.post(reverse("accounts:hospital-signup"), {
            "name": "New Hospital", "login_id": "new-language-hospital",
            "password": "StrongPassword!2026",
            "terms_agreed": True, "privacy_agreed": True,
            "overseas_info_agreed": True,
            "country": "US", "city": "Boston", "address": "Boston",
            "phone": "123456789", "preferred_language": "en",
            "specialties": [{"specialty_code": SpecialtyCode.ACNE_SCAR}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="new-language-hospital")
        self.client.force_authenticate(user)
        profile = self.client.get(self.url)
        self.assertEqual(profile.data["preferred_language"], "en")
        self.assertEqual(profile.data["language_code"], "en")


class HospitalLanguageMigrationTests(TransactionTestCase):
    old_target = ("accounts", "0012_alter_hospitalprofile_country_and_more")
    new_target = ("accounts", "0013_remove_hospitalprofile_language_code")

    def test_existing_account_language_survives_legacy_field_removal(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([self.old_target])
            apps = executor.loader.project_state([self.old_target]).apps
            OldUser = apps.get_model("accounts", "User")
            OldProfile = apps.get_model("accounts", "HospitalProfile")
            ids = []
            for index, (language, legacy) in enumerate([
                ("ko", "ja"), ("ja", "en"), ("zh", "unsupported"), ("en", "en"),
            ]):
                user = OldUser.objects.create(
                    username=f"migration-language-{index}",
                    name="Hospital", user_type="HOSPITAL",
                    preferred_language=language,
                )
                OldProfile.objects.create(
                    user=user, country="JP", city="Tokyo", address="Tokyo",
                    language_code=legacy,
                )
                ids.append((user.pk, language))

            executor = MigrationExecutor(connection)
            executor.migrate([self.new_target])
            for user_id, expected in ids:
                self.assertEqual(
                    User.objects.get(pk=user_id).preferred_language, expected,
                )
            columns = {
                column.name for column in connection.introspection
                .get_table_description(connection.cursor(), "accounts_hospitalprofile")
            }
            self.assertNotIn("language_code", columns)
        finally:
            MigrationExecutor(connection).migrate(latest)
