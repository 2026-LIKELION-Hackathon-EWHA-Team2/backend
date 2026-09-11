from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from .countries import normalize_country


#API요청 시 국가값 정규화
class CountryCodeField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)

        try:
            return normalize_country(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

class LatitudeField(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(
            max_digits=10, decimal_places=7, min_value=-90, max_value=90, **kwargs,
        )


class LongitudeField(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(
            max_digits=10, decimal_places=7, min_value=-180, max_value=180, **kwargs,
        )


def validate_api_coordinates(latitude, longitude, *, optional=False,
                             names=("latitude", "longitude")):
    from .validators import validate_coordinate_pair

    try:
        return validate_coordinate_pair(
            latitude, longitude, optional=optional, names=names,
        )
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.message_dict) from error


class ProfileCoordinatesSerializerMixin(serializers.Serializer):
    latitude = LatitudeField(required=False, allow_null=True)
    longitude = LongitudeField(required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        validate_api_coordinates(
            attrs.get("latitude", getattr(self.instance, "latitude", None)),
            attrs.get("longitude", getattr(self.instance, "longitude", None)),
            optional=True,
        )
        return attrs
