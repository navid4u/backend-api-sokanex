from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("accounts", "0017_repair_approved_premium_levels")]

    operations = [
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="assessment_version",
            field=models.CharField(db_index=True, default="LEGACY_V1", max_length=40),
        ),
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="asset_inventory",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="raw_scores",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="percentages",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="dominant_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CAPITAL_GUARDIAN", "محافظ سرمایه"),
                    ("BALANCED_SMART", "متعادل و هوشمند"),
                    ("FUTURE_GROWTH", "رشدطلب آینده‌نگر"),
                    ("OPPORTUNITY_SEEKER", "فرصت‌جو"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="dominant_percentage",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="financialpersonalityassessment",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="financialpersonalityassessment",
            name="personality_type",
            field=models.CharField(
                choices=[
                    ("WEALTH_ARCHITECT", "معمار ثروت"),
                    ("CAPITAL_GUARDIAN", "نگهبان سرمایه"),
                    ("OPPORTUNITY_HUNTER", "شکارچی فرصت"),
                    ("DISCIPLINED_NAVIGATOR", "ناوبر منضبط"),
                    ("MARKET_EXPLORER", "کاوشگر بازار"),
                    ("BALANCED_SMART", "متعادل و هوشمند"),
                    ("FUTURE_GROWTH", "رشدطلب آینده‌نگر"),
                    ("OPPORTUNITY_SEEKER", "فرصت‌جو"),
                ],
                max_length=30,
            ),
        ),
    ]
