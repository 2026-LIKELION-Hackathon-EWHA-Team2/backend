from django.core.exceptions import ValidationError

from accounts.validators import finite_number


WEIGHT_FIELDS = ("specialty_weight", "distance_weight", "collaboration_weight")
SCORE_FIELDS = ("specialty_score", "distance_score", "collaboration_score", "total_score")
DISTANCE_MAX = 99999999.99


class NumericDataError(ValueError):
    """Invalid server-side recommendation input or calculation result."""


def validate_weight(value):
    finite_number(value, 0, 100, integer=True)


def validate_score(value):
    finite_number(value, 0, 100)


def validate_distance(value):
    finite_number(value, 0, DISTANCE_MAX)


def validate_rank(value):
    finite_number(value, 1, 32767, integer=True)


def validate_count(value):
    finite_number(value, 0, 2147483647, integer=True)


def validate_weights(values):
    errors = {}
    for field, value in zip(WEIGHT_FIELDS, values):
        try:
            validate_weight(value)
        except ValidationError as error:
            errors[field] = error.messages
    if not errors and not any(values):
        errors = {field: ["최소 한 개의 가중치는 0보다 커야 합니다."] for field in WEIGHT_FIELDS}
    if errors:
        raise ValidationError(errors)


def validate_recommendation_values(values):
    validators = {
        **dict.fromkeys(SCORE_FIELDS, validate_score),
        "distance_km": validate_distance,
        "batch_number": validate_rank,
        "rank_number": validate_rank,
        "collaboration_count": validate_count,
    }
    for field, validator in validators.items():
        if field not in values or (field == "distance_km" and values[field] is None):
            continue
        try:
            validator(values[field])
        except ValidationError as error:
            raise NumericDataError(f"{field}: {error.messages}") from error
