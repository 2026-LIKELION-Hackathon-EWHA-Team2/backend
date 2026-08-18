from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matching", "0005_hospitalrecommendation_collaboration_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospitalrecommendation",
            name="selection_source",
            field=models.CharField(
                choices=[
                    ("AI_RECOMMENDATION", "AI 추천"),
                    ("NETWORK", "네트워크 병원"),
                ],
                default="AI_RECOMMENDATION",
                max_length=30,
            ),
        ),
    ]
