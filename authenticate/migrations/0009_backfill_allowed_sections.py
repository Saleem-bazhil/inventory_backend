from django.db import migrations

# Every section a user can be granted. Mirrors the sidebar nav (and the SECTIONS
# list the frontend renders the permission checkboxes from).
ALL_SECTIONS = [
    "/",
    "/customers",
    "/cso-entry",
    "/engineers",
    "/quotation",
    "/part-request",
    "/invoice",
    "/stock",
    "/hp-stock",
    "/hp-stock-rma",
    "/buffer",
    "/purchase-order",
    "/reports",
    "/activity-charges",
    "/settings",
]

# Roles that bypass section checks entirely — no point backfilling them.
BYPASS_ROLES = ["super_admin", "admin"]


def backfill(apps, schema_editor):
    """Grant every section to existing users who have no explicit list yet.

    Section access used to be enforced for managers only; everyone else saw the
    whole sidebar. Enforcement now covers all roles, so users with an empty
    `allowed_sections` would suddenly be locked out of everything. Backfilling the
    full list keeps them exactly where they were — an admin can uncheck from there.

    Managers already carry a deliberate list, so a non-empty list is never touched.
    """
    UserProfile = apps.get_model("authenticate", "UserProfile")
    for profile in UserProfile.objects.exclude(role__in=BYPASS_ROLES):
        if not profile.allowed_sections:
            profile.allowed_sections = list(ALL_SECTIONS)
            profile.save(update_fields=["allowed_sections"])


def noop(apps, schema_editor):
    """Nothing to undo — the pre-migration state is an empty list, which is also
    a valid post-migration state (it just means "no sections")."""


class Migration(migrations.Migration):

    dependencies = [
        ("authenticate", "0008_userprofile_allowed_sections"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
