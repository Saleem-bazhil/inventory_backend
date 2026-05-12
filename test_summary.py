import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ainventory.settings")
django.setup()

from authenticate.models import UserProfile
from quotation.models import Quotation
from django.db.models import Count

print("Starting diagnostic...")

# Print defined regions
print(f"Region choices: {UserProfile.REGION_CHOICES}")

# Run summary query logic
qs = Quotation.objects.all()
total = qs.count()
print(f"Total quotations in DB: {total}")

region_list = []
for code, label in UserProfile.REGION_CHOICES:
    count = qs.filter(ticket__region=code).count()
    region_list.append({
        'region': code,
        'total': count
    })
    print(f"  - {label} ({code}): {count}")

print(f"Grand total output: {sum(r['total'] for r in region_list)} vs actual count {total}")

# Wait, could some quotations NOT be linked to a ticket correctly?
missing_ticket = qs.filter(ticket__isnull=True).count()
print(f"Quotations missing tickets: {missing_ticket}")
