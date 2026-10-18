from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academy", "0005_course_currency_course_is_free_course_price_and_more")]

    operations = [
        migrations.AddField(
            model_name="course", name="market",
            field=models.CharField(blank=True, choices=[
                ("internal", "Internal"), ("forex", "Forex"), ("crypto", "Crypto"),
            ], db_index=True, default="", max_length=12),
        ),
    ]
