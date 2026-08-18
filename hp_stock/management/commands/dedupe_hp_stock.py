"""Remove the duplicate part rows the OpenCall sync created while it was blind.

Between 2026-08-17 and 2026-08-18 the received-spare filter hid unclassified
rows from `GET /hp-stock/items/?search=<case_id>` - the lookup the sync uses to
decide update-vs-create. Every row it could not see, it created again, and the
new row was hidden too, so it happened again on the next 15-minute cycle.

A duplicate is a second row for the same case AND the same part. Part identity
mirrors the sync's own rule (`itemMatchesPart` in inventorySyncService): the
Part Order No, falling back to the Good Part No. Rows carrying neither are
grouped under a blank key, which is what the sync's "unkeyed part" is.

SAFE BY DEFAULT - a dry run that only reports. Pass --apply to delete.

What it will NEVER delete, so no real work is lost:
  - the oldest row of a group (every case keeps its original)
  - anything past Stock Entry - somebody moved it through the workflow
  - anything with transition history, a good-part photo or a return photo
  - anything created before --since (default 2026-08-17, when this started)

Duplicates that fail those guards are reported separately, not deleted: if an
employee photographed a part on the duplicate rather than the original, that
row is a human decision, not a script's.

    python manage.py dedupe_hp_stock                    # dry run
    python manage.py dedupe_hp_stock --apply            # delete
    python manage.py dedupe_hp_stock --since 2026-08-16 # widen the window
"""
from collections import defaultdict
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hp_stock.models import HPStockItem

# The day the sync went blind. Rows older than this predate the incident and are
# left alone even when they look duplicated - they are somebody else's problem,
# and deleting them is not what this command was reviewed for.
DEFAULT_SINCE = date(2026, 8, 17)

SAMPLE_ROWS = 15


def part_key(row):
    """A part's identity within a case - Part Order No, else Good Part No.

    Mirrors `itemMatchesPart` in the sync, so this command groups rows exactly
    the way the sync decides two rows are the same part. '' is a real key: it is
    the sync's "unkeyed" part, and two unkeyed rows on one case are duplicates
    of each other.
    """
    order = (row['part_order_number'] or '').strip().upper()
    if order:
        return order
    return (row['good_part_number'] or '').strip().upper()


class Command(BaseCommand):
    help = "Report (or delete) duplicate HP Stock rows created by the blind sync."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help="Actually delete. Without it nothing is written.",
        )
        parser.add_argument(
            '--since', default=DEFAULT_SINCE.isoformat(),
            help="Only delete duplicates created on/after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            '--region', default='',
            help="Restrict to one region. Default: every region.",
        )

    def handle(self, *args, **options):
        try:
            since = datetime.strptime(options['since'], '%Y-%m-%d').date()
        except ValueError:
            raise CommandError("--since must be YYYY-MM-DD")

        apply_changes = options['apply']
        region = options['region'].strip()

        queryset = HPStockItem.objects.all()
        if region:
            queryset = queryset.filter(region=region)

        rows = list(queryset.values(
            'id', 'case_id', 'good_part_number', 'part_order_number', 'status',
            'region', 'transition_history', 'created_at', 'good_part_image',
            'return_part_image',
        ))
        self.stdout.write(f"[Dedupe] rows in scope: {len(rows)}")

        groups = defaultdict(list)
        for row in rows:
            groups[(row['case_id'], part_key(row))].append(row)

        deletable = []
        protected = []  # duplicates a guard saved - reported, never deleted
        for members in groups.values():
            if len(members) < 2:
                continue
            # Oldest first: the original is the keeper. created_at can tie on a
            # bulk insert, so id breaks the tie - it is monotonic.
            members.sort(key=lambda r: (r['created_at'], r['id']))
            for row in members[1:]:
                reason = self._protected_reason(row, since)
                if reason:
                    protected.append((row, reason))
                else:
                    deletable.append(row)

        self._report(groups, deletable, protected)

        if not deletable:
            self.stdout.write(self.style.SUCCESS("\n[Dedupe] nothing to delete."))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "\n[Dedupe] DRY RUN - nothing written. Re-run with --apply."
            ))
            return

        ids = [row['id'] for row in deletable]
        with transaction.atomic():
            deleted, _ = HPStockItem.objects.filter(id__in=ids).delete()
        self.stdout.write(self.style.SUCCESS(
            f"\n[Dedupe] deleted {deleted} rows."
        ))

    def _protected_reason(self, row, since):
        """Why this duplicate must survive, or None when it is safe to delete."""
        created = row['created_at']
        if timezone.is_aware(created):
            created = timezone.localtime(created)
        if created.date() < since:
            return 'predates the incident window'
        if row['status'] != 'PENDING':
            return 'workflow already moved past Stock Entry'
        if row['transition_history']:
            return 'has transition history'
        if row['good_part_image'] or row['return_part_image']:
            return 'has a photo attached'
        return None

    def _report(self, groups, deletable, protected):
        dup_groups = sum(1 for members in groups.values() if len(members) > 1)
        self.stdout.write(
            f"[Dedupe] case+part groups: {len(groups)}, "
            f"with duplicates: {dup_groups}"
        )
        self.stdout.write(
            f"[Dedupe] duplicates deletable: {len(deletable)}, "
            f"kept by a guard: {len(protected)}"
        )

        by_region = defaultdict(int)
        for row in deletable:
            by_region[row['region'] or '(no region)'] += 1
        if by_region:
            self.stdout.write("\nREGION            TO DELETE")
            for name in sorted(by_region):
                self.stdout.write(f"{name:<18}{by_region[name]}")
            self.stdout.write(f"{'TOTAL':<18}{len(deletable)}")

        if deletable:
            self.stdout.write("\nSample [would delete]:")
            for row in deletable[:SAMPLE_ROWS]:
                self.stdout.write(
                    f"  id={row['id']} case={row['case_id']} "
                    f"part={part_key(row) or '-'} region={row['region']} "
                    f"created={row['created_at']:%Y-%m-%d %H:%M}"
                )

        # These are the ones worth a human's eyes: a duplicate somebody worked
        # on. If an employee photographed a part on the duplicate instead of the
        # original, the case now has two live rows and only a person can say
        # which one is the real stock.
        if protected:
            self.stdout.write(self.style.WARNING(
                "\nSample [duplicate, but kept - review these]:"
            ))
            for row, reason in protected[:SAMPLE_ROWS]:
                self.stdout.write(
                    f"  id={row['id']} case={row['case_id']} "
                    f"part={part_key(row) or '-'} status={row['status']} "
                    f"-> {reason}"
                )
