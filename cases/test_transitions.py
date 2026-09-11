from types import SimpleNamespace

from django.test import SimpleTestCase

from .domain.transitions import (
    ensure_agreement_editable,
    ensure_agreement_reviewable,
    ensure_collaboration_acceptable,
    ensure_transfer_reviewable,
    ensure_transfer_sendable,
)
from .exceptions import InvalidStateTransitionError
from .models import (
    CaseAgreement,
    CaseCollaborationRequest,
    CaseTransfer,
)


class CaseStateTransitionTests(SimpleTestCase):
    def test_review_required_transfer_can_be_reviewed(self):
        transfer = SimpleNamespace(status=CaseTransfer.Status.REVIEW_REQUIRED)

        ensure_transfer_reviewable(transfer, (True, True, True))

    def test_transfer_cannot_be_reviewed_without_all_agreements(self):
        transfer = SimpleNamespace(status=CaseTransfer.Status.REVIEW_REQUIRED)

        with self.assertRaises(InvalidStateTransitionError):
            ensure_transfer_reviewable(transfer, (True, False, True))

    def test_only_ready_transfer_can_be_sent(self):
        transfer = SimpleNamespace(
            status=CaseTransfer.Status.REVIEW_REQUIRED,
            procedure_medication_agreed=True,
            adverse_effect_clinician_note_agreed=True,
            overseas_ai_processing_agreed=True,
            include_patient_info=True,
            include_procedure_info=False,
            include_adverse_effects=False,
            include_clinician_note=False,
        )

        with self.assertRaises(InvalidStateTransitionError):
            ensure_transfer_sendable(transfer)

    def test_only_requested_collaboration_can_be_accepted(self):
        collaboration_request = SimpleNamespace(
            status=CaseCollaborationRequest.Status.COMPLETED,
        )

        with self.assertRaises(InvalidStateTransitionError):
            ensure_collaboration_acceptable(collaboration_request)

    def test_final_agreement_cannot_be_edited_or_reviewed(self):
        agreement = SimpleNamespace(status=CaseAgreement.Status.FINAL)

        with self.assertRaises(InvalidStateTransitionError):
            ensure_agreement_editable(agreement)
        with self.assertRaises(InvalidStateTransitionError):
            ensure_agreement_reviewable(agreement)
