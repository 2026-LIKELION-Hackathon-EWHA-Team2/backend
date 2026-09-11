from rest_framework.exceptions import ValidationError


class CaseDomainError(ValidationError):
    """Base exception for an invalid cases-domain operation."""


class InvalidStateTransitionError(CaseDomainError):
    """Raised when an action is not allowed in the current state."""


class StateConsistencyError(CaseDomainError):
    """Raised when related case records contradict each other."""


class DuplicateCaseActionError(CaseDomainError):
    """Raised when a non-repeatable case action is requested again."""
