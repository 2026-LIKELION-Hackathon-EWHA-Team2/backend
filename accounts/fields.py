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