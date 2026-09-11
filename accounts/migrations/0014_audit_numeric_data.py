"""Validate historical values before either app adds numeric constraints."""
from decimal import Decimal, InvalidOperation

from django.db import migrations


def audit_numeric_data(apps, schema_editor):
    errors = []
    connection = schema_editor.connection

    def number(value, low, high, integer=False):
        try:
            result = Decimal(str(value))
            return (
                result.is_finite() and Decimal(str(low)) <= result <= Decimal(str(high))
                and (not integer or result == result.to_integral_value())
            )
        except (InvalidOperation, ValueError, TypeError):
            return False

    targets = [
        ("accounts", "PatientProfile", "latitude", "longitude", True, {}),
        ("accounts", "HospitalProfile", "latitude", "longitude", True, {}),
        ("matching", "HospitalMatchRequest", "search_latitude", "search_longitude", False, {
            "specialty_weight": (0, 100, True),
            "distance_weight": (0, 100, True),
            "collaboration_weight": (0, 100, True),
        }),
        ("matching", "HospitalRecommendation", None, None, False, {
            "specialty_score": (0, 100, False),
            "distance_score": (0, 100, False),
            "collaboration_score": (0, 100, False),
            "total_score": (0, 100, False),
            "distance_km": (0, "99999999.99", False),
            "batch_number": (1, 32767, True),
            "rank_number": (1, 32767, True),
            "collaboration_count": (0, 2147483647, True),
        }),
    ]
    for app, model_name, lat, lon, optional, limits in targets:
        model = apps.get_model(app, model_name)
        names = ([lat, lon] if lat else []) + list(limits)
        columns = [model._meta.pk.column] + [
            model._meta.get_field(name).column for name in names
        ]
        quote = connection.ops.quote_name
        # Raw numeric columns avoid ORM Decimal conversion hiding malformed values.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT " + ", ".join(map(quote, columns))
                + " FROM " + quote(model._meta.db_table)
            )
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                for row in rows:
                    values = dict(zip(names, row[1:]))
                    invalid = []
                    if lat:
                        both_missing = values[lat] is None and values[lon] is None
                        if not (optional and both_missing):
                            for field, limit in ((lat, 90), (lon, 180)):
                                if not number(values[field], -limit, limit):
                                    invalid.append(field)
                    for field, bounds in limits.items():
                        if field == "distance_km" and values[field] is None:
                            continue
                        if not number(values[field], *bounds):
                            invalid.append(field)
                    if model_name == "HospitalMatchRequest" and not invalid:
                        if sum(Decimal(str(values[field])) for field in limits) == 0:
                            invalid.append("weights")
                    if invalid and len(errors) < 20:
                        errors.append(f"{app}.{model_name} pk={row[0]}: {', '.join(invalid)}")
    if errors:
        raise RuntimeError(
            "Invalid numeric data. Correct the listed records before migrating "
            "(up to 20 shown; no values have been changed):\n" + "\n".join(errors)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_remove_hospitalprofile_language_code"),
        ("matching", "0007_alter_hospitalmatchrequest_search_country"),
    ]
    operations = [
        migrations.RunPython(audit_numeric_data, migrations.RunPython.noop),
    ]
