import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0007_casetransfer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicalcase",
            name="partner_hospital",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="received_cases",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
