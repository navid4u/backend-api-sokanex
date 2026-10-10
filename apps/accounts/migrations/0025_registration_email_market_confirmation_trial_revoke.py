from django.db import migrations, models
from django.db.models import Count, Min, Q
from django.db.models.functions import Lower, Trim


def backfill_explicit_market_selection(apps, schema_editor):
    Preference = apps.get_model("accounts", "UserMarketPreference")
    Profile = apps.get_model("accounts", "UserAccessProfile")
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias
    evidence = list(
        Preference.objects.using(database)
        .filter(market__in=("internal", "forex", "crypto"))
        .values("user_id")
        .annotate(first_selected_at=Min("selected_at"))
    )
    if not evidence:
        return
    excluded = set(
        User.objects.using(database)
        .filter(Q(is_superuser=True) | Q(role__in=("SUPER_ADMIN", "SUPPORT")))
        .values_list("id", flat=True)
    )
    selected_at = {
        row["user_id"]: row["first_selected_at"]
        for row in evidence if row["user_id"] not in excluded
    }
    existing = {
        profile.user_id: profile
        for profile in Profile.objects.using(database).filter(user_id__in=selected_at)
    }
    to_create = []
    to_update = []
    for user_id, timestamp in selected_at.items():
        profile = existing.get(user_id)
        if profile is None:
            to_create.append(Profile(user_id=user_id, market_selection_confirmed_at=timestamp))
        elif profile.market_selection_confirmed_at is None:
            profile.market_selection_confirmed_at = timestamp
            to_update.append(profile)
    Profile.objects.using(database).bulk_create(to_create, batch_size=500)
    Profile.objects.using(database).bulk_update(
        to_update, ["market_selection_confirmed_at"], batch_size=500
    )


def reject_duplicate_emails(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    duplicates = (
        User.objects.using(schema_editor.connection.alias)
        .exclude(email="")
        .annotate(normalized_email=Lower(Trim("email")))
        .values("normalized_email")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .count()
    )
    if duplicates:
        raise RuntimeError(
            f"Registration email uniqueness needs review: {duplicates} duplicate email groups exist. "
            "Resolve them before this migration; no account was changed."
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0024_marketaccessrequest")]

    operations = [
        migrations.AddField(
            model_name="trialgrant",
            name="revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_explicit_market_selection, migrations.RunPython.noop),
        migrations.RunPython(reject_duplicate_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower(Trim("email")), condition=~Q(email=""), name="accounts_user_email_ci_uniq"
            ),
        ),
    ]
