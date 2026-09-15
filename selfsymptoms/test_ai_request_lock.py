from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import PatientProfile, User

from .ai_request_lock import (
    AIRequestInProgress,
    symptom_case_ai_request_lock,
)
from .models import PatientSymptomCase, SymptomCaseAIRequestLock


class SymptomCaseAIRequestLockTests(APITestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="ai-lock-patient",
            password="StrongPassword!2026",
            name="Patient",
            user_type=User.UserType.PATIENT,
        )
        patient = PatientProfile.objects.create(user=user)
        self.symptom_case = PatientSymptomCase.objects.create(
            patient=patient,
        )

    def test_concurrent_operation_is_rejected_and_lock_is_released(self):
        operation = (
            SymptomCaseAIRequestLock.Operation.HOSPITAL_MATCHING
        )

        with symptom_case_ai_request_lock(
            symptom_case=self.symptom_case,
            operation=operation,
            detail="이미 처리 중입니다.",
        ):
            self.assertTrue(SymptomCaseAIRequestLock.objects.exists())

            with self.assertRaises(AIRequestInProgress):
                with symptom_case_ai_request_lock(
                    symptom_case=self.symptom_case,
                    operation=operation,
                    detail="이미 처리 중입니다.",
                ):
                    pass

        self.assertFalse(SymptomCaseAIRequestLock.objects.exists())

    def test_lock_is_released_when_processing_raises(self):
        with self.assertRaises(RuntimeError):
            with symptom_case_ai_request_lock(
                symptom_case=self.symptom_case,
                operation=(
                    SymptomCaseAIRequestLock.Operation.CASE_TRANSFER
                ),
                detail="이미 처리 중입니다.",
            ):
                raise RuntimeError("processing failed")

        self.assertFalse(SymptomCaseAIRequestLock.objects.exists())

    def test_expired_lock_can_be_reclaimed(self):
        operation = SymptomCaseAIRequestLock.Operation.CASE_TRANSFER
        SymptomCaseAIRequestLock.objects.create(
            symptom_case=self.symptom_case,
            operation=operation,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        with symptom_case_ai_request_lock(
            symptom_case=self.symptom_case,
            operation=operation,
            detail="이미 처리 중입니다.",
        ):
            lock = SymptomCaseAIRequestLock.objects.get()
            self.assertGreater(lock.expires_at, timezone.now())

        self.assertFalse(SymptomCaseAIRequestLock.objects.exists())
