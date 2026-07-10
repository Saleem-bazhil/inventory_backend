"""Strip expiring S3 signature query-strings from stored image URLs.

Earlier uploads saved *signed* S3 URLs (…?X-Amz-Signature=…) into each
HPStockItem.transition_history entry. Those links expire (7-day max) and then
return AccessDenied. Now that the bucket serves public, permanent URLs, we
drop the query-string so the stored links point at the durable object URL.
"""
from django.db import migrations


def _strip(url):
    if isinstance(url, str) and "?X-Amz-" in url:
        return url.split("?", 1)[0]
    return url


def strip_signed_urls(apps, schema_editor):
    HPStockItem = apps.get_model("hp_stock", "HPStockItem")
    for item in HPStockItem.objects.exclude(transition_history=[]).iterator():
        history = item.transition_history or []
        changed = False
        for entry in history:
            if not isinstance(entry, dict):
                continue
            for key in ("image", "image_back"):
                if key in entry:
                    new = _strip(entry[key])
                    if new != entry[key]:
                        entry[key] = new
                        changed = True
        if changed:
            item.transition_history = history
            item.save(update_fields=["transition_history"])


class Migration(migrations.Migration):

    dependencies = [
        ("hp_stock", "0023_merge_20260710_1111"),
    ]

    operations = [
        # Data-only fix; nothing to reverse (URLs already point at the object).
        migrations.RunPython(strip_signed_urls, migrations.RunPython.noop),
    ]
