from django.db import migrations


def restore_reviewed_versions(apps, schema_editor):
    CaseAgreementReview = apps.get_model(
        "cases",
        "CaseAgreementReview",
    )
    CaseAgreementRevision = apps.get_model(
        "cases",
        "CaseAgreementRevision",
    )

    for review in CaseAgreementReview.objects.iterator():
        first_later_revision = (
            CaseAgreementRevision.objects.filter(
                agreement_id=review.agreement_id,
                edited_at__gt=review.reviewed_at,
            )
            .order_by("edited_at", "id")
            .first()
        )

        if (
            first_later_revision is not None
            and review.reviewed_version
            != first_later_revision.version
        ):
            CaseAgreementReview.objects.filter(pk=review.pk).update(
                reviewed_version=first_later_revision.version,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0018_caseagreement_opinion_translation"),
    ]

    operations = [
        migrations.RunPython(
            restore_reviewed_versions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
