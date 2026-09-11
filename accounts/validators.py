from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import models


def finite_number(value, minimum, maximum, *, integer=False):
    try:
        if isinstance(value, bool):
            raise ValueError
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("유효한 숫자를 입력해주세요.") from None
    minimum, maximum = Decimal(str(minimum)), Decimal(str(maximum))
    if not number.is_finite() or not minimum <= number <= maximum:
        raise ValidationError(f"{minimum} 이상 {maximum} 이하의 유한한 숫자여야 합니다.")
    if integer and number != number.to_integral_value():
        raise ValidationError("정수를 입력해주세요.")
    return number


def coordinate(value, limit):
    number = finite_number(value, -limit, limit)
    DecimalValidator(max_digits=10, decimal_places=7)(number)
    return number


def validate_latitude(value):
    coordinate(value, 90)


def validate_longitude(value):
    coordinate(value, 180)


def validate_coordinate_pair(latitude, longitude, *, optional=False,
                             names=("latitude", "longitude")):
    if optional and latitude is None and longitude is None:
        return None, None
    errors = {}
    values = []
    for name, value, limit in zip(names, (latitude, longitude), (90, 180)):
        try:
            if value is None:
                raise ValidationError("위도와 경도를 함께 입력해주세요.")
            values.append(coordinate(value, limit))
        except ValidationError as error:
            errors[name] = error.messages
    if errors:
        raise ValidationError(errors)
    return tuple(values)


def coordinate_constraint(name, latitude="latitude", longitude="longitude",
                          *, optional=False):
    valid = models.Q(**{
        f"{latitude}__isnull": False, f"{longitude}__isnull": False,
        f"{latitude}__gte": -90, f"{latitude}__lte": 90,
        f"{longitude}__gte": -180, f"{longitude}__lte": 180,
    })
    if optional:
        valid |= models.Q(**{
            f"{latitude}__isnull": True, f"{longitude}__isnull": True,
        })
    return models.CheckConstraint(condition=valid, name=name)
