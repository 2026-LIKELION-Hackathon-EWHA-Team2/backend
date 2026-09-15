import uuid
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from .models import PatientSymptomCase, SymptomCaseAIRequestLock


class AIRequestInProgress(APIException):
    status_code = 409
    default_detail = "이미 동일한 AI 요청이 처리 중입니다."
    default_code = "ai_request_in_progress"


def _acquire_ai_request_lock(*, symptom_case, operation):
    now = timezone.now()
    expires_at = now + timedelta(
        seconds=settings.AI_REQUEST_LOCK_TIMEOUT_SECONDS,
    )
    token = uuid.uuid4()

    try:
        with transaction.atomic():
            SymptomCaseAIRequestLock.objects.create(
                symptom_case=symptom_case,
                operation=operation,
                token=token,
                expires_at=expires_at,
            )
    except IntegrityError:
        reclaimed = SymptomCaseAIRequestLock.objects.filter(
            symptom_case=symptom_case,
            operation=operation,
            expires_at__lte=now,
        ).update(
            token=token,
            expires_at=expires_at,
            updated_at=now,
        )
        if not reclaimed:
            raise AIRequestInProgress

    return token


def _release_ai_request_lock(*, symptom_case, operation, token):
    SymptomCaseAIRequestLock.objects.filter(
        symptom_case=symptom_case,
        operation=operation,
        token=token,
    ).delete()


@contextmanager
def symptom_case_ai_request_lock(*, symptom_case, operation, detail):
    try:
        token = _acquire_ai_request_lock(
            symptom_case=symptom_case,
            operation=operation,
        )
    except AIRequestInProgress as exc:
        raise AIRequestInProgress(detail=detail) from exc

    try:
        yield
    finally:
        _release_ai_request_lock(
            symptom_case=symptom_case,
            operation=operation,
            token=token,
        )


def prevent_duplicate_ai_requests(*, operation, request_field, detail):
    def decorator(view_method):
        @wraps(view_method)
        def wrapped(view, request, *args, **kwargs):
            symptom_case_id = request.data.get(request_field)

            try:
                symptom_case = PatientSymptomCase.objects.get(
                    symptom_case_id=symptom_case_id,
                    patient__user=request.user,
                )
            except (
                PatientSymptomCase.DoesNotExist,
                TypeError,
                ValueError,
            ):
                return view_method(view, request, *args, **kwargs)

            with symptom_case_ai_request_lock(
                symptom_case=symptom_case,
                operation=operation,
                detail=detail,
            ):
                return view_method(view, request, *args, **kwargs)

        return wrapped

    return decorator
