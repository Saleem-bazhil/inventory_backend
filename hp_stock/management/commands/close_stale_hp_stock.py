"""Close HP Stock rows whose OpenCall case is finished in the field.

Nothing retires an HP Stock row today. The sync creates one per part case at
Stock Entry, and the only way out is a person walking it to "Close the Case" -
which is why Active Cases holds thousands of rows against roughly a hundred
genuinely live ones. The backlog is real work that finished months ago and was
never closed here.

OpenCall already pushes the answer: `OpencallActivePartCase` is the list of case
ids that are active as of its newest report. A row whose case is NOT on that
list is done in the field.

SAFE BY DEFAULT - a dry run that only reports. Pass --apply to close.

What it will NEVER close, so nothing in flight is lost:
  - a part still out with an engineer (issued, not yet handed back) - the
    Pending Return card exists to chase exactly these, and closing one would
    erase the fact that somebody is still holding it
  - a DC Cut request, which is waiting on an approval, not on the field
  - a part somebody received and handled but never issued (stock-checked or
    photographed). The case being over does not put that spare back on a van -
    it is sitting in a warehouse, and a person has to decide whether it goes
    back to HP. Pass --include-in-stock to close these too.
  - anything already closed
  - anything newer than --grace-days (default 7), so one bad daily report
    cannot sweep the board

It also refuses to run at all if OpenCall has pushed no active-case list: an
empty list means "we do not know", not "nothing is active", and treating those
the same would close every row in the table.

Each close is written to transition_history in the same shape the workflow
writes, so the audit trail reads normally and says who did it.

    python manage.py close_stale_hp_stock                  # report
    python manage.py close_stale_hp_stock --apply          # close
    python manage.py close_stale_hp_stock --grace-days 30  # be more cautious
"""
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hp_stock.models import HPStockItem, OpencallActivePartCase
from hp_stock.views import PENDING_RETURN_STATUSES, opencall_active_case_ids

SAMPLE_ROWS = 15
ACTOR = "System (OpenCall reconcile)"

# Received and handled, but never issued to anybody. Someone physically had this
# part in their hands to check it in or photograph it, and no engineer ever took
# it - so it is still on a shelf. That is a real asset, not a stale record, and
# closing it silently is how stock goes missing on paper.
IN_STOCK_STATUSES = ['STOCK_CHECK', 'GOOD_PART_PHOTO']


class Command(BaseCommand):
    help = "Close HP Stock rows whose OpenCall case is no longer active."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help="Actually close. Without it nothing is written.",
        )
        parser.add_argument(
            '--grace-days', type=int, default=7,
            help="Leave rows younger than this alone (default 7).",
        )
        parser.add_argument(
            '--include-in-stock', action='store_true',
            help="Also close parts received but never issued (default: keep).",
        )
        parser.add_argument(
            '--region', default='',
            help="Restrict to one region. Default: every region.",
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        grace_days = options['grace_days']
        include_in_stock = options['include_in_stock']
        region = options['region'].strip()

        if grace_days < 0:
            raise CommandError("--grace-days cannot be negative")

        # "We were never told" is not "nothing is active". Without this the very
        # first run on a fresh database would close the entire table.
        active_ids = opencall_active_case_ids()
        if active_ids is None:
            raise CommandError(
                "OpenCall has pushed no active part-case list - refusing to run. "
                "Without it every row looks finished."
            )
        active = set(active_ids)
        if not active:
            raise CommandError(
                "OpenCall's newest report lists zero active cases - refusing to "
                "run. Check the OpenCall push before trusting this."
            )
        latest = OpencallActivePartCase.objects.order_by('-report_date').values_list(
            'report_date', flat=True,
        ).first()
        self.stdout.write(
            f"[Close] OpenCall active cases: {len(active)} (report {latest})"
        )

        cutoff = timezone.now() - timedelta(days=grace_days)

        queryset = HPStockItem.objects.exclude(status__in=['CLOSED', 'DC_CUT_REQUEST'])
        if region:
            queryset = queryset.filter(region=region)

        rows = list(queryset.values(
            'id', 'case_id', 'status', 'region', 'created_at', 'case_created_time',
        ))
        self.stdout.write(f"[Close] open rows in scope: {len(rows)}")

        closable, held = [], []
        for row in rows:
            reason = self._held_reason(row, active, cutoff, include_in_stock)
            if reason:
                held.append((row, reason))
            else:
                closable.append(row)

        self._report(closable, held)

        if not closable:
            self.stdout.write(self.style.SUCCESS("\n[Close] nothing to close."))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "\n[Close] DRY RUN - nothing written. Re-run with --apply."
            ))
            return

        closed = self._close(closable)
        self.stdout.write(self.style.SUCCESS(f"\n[Close] closed {closed} rows."))

    def _held_reason(self, row, active, cutoff, include_in_stock):
        """Why this row must stay open, or None when it is safe to close."""
        if row['case_id'] in active:
            return 'case is still active in OpenCall'
        if row['status'] in PENDING_RETURN_STATUSES:
            return 'part is still out with an engineer'
        if not include_in_stock and row['status'] in IN_STOCK_STATUSES:
            return 'part was received but never issued - review'
        # case_created_time is the field date and is the honest age of the work;
        # created_at is when the sync first saw it and is the fallback.
        age_from = row['case_created_time'] or row['created_at']
        if age_from and age_from > cutoff:
            return 'inside the grace period'
        return None

    def _close(self, closable):
        """Close in one transaction, each with a history entry the UI can read."""
        now = timezone.now()
        stamp = now.isoformat()
        ids = [row['id'] for row in closable]
        closed = 0
        with transaction.atomic():
            # Re-read under the transaction so the history is appended to the
            # row's real current value, not the snapshot taken for the report.
            for item in HPStockItem.objects.select_for_update().filter(id__in=ids):
                history = list(item.transition_history or [])
                history.append({
                    "from_status": item.status,
                    "to_status": "CLOSED",
                    "comment": "Auto-closed: case no longer active in OpenCall.",
                    "updated_by": ACTOR,
                    "timestamp": stamp,
                })
                item.transition_history = history
                item.status = 'CLOSED'
                item.save(update_fields=['status', 'transition_history', 'updated_at'])
                closed += 1
        return closed

    def _report(self, closable, held):
        self.stdout.write(
            f"[Close] to close: {len(closable)}, staying open: {len(held)}"
        )

        by_region = defaultdict(int)
        by_status = defaultdict(int)
        for row in closable:
            by_region[row['region'] or '(no region)'] += 1
            by_status[row['status']] += 1

        if by_region:
            self.stdout.write("\nREGION            TO CLOSE")
            for name in sorted(by_region):
                self.stdout.write(f"{name:<18}{by_region[name]}")
            self.stdout.write(f"{'TOTAL':<18}{len(closable)}")

            self.stdout.write("\nFROM STATUS       COUNT")
            for name in sorted(by_status):
                self.stdout.write(f"{name:<18}{by_status[name]}")

        # Anything not at Stock Entry is worth a glance before --apply: it means
        # somebody had started the workflow and stopped partway.
        started = [r for r in closable if r['status'] != 'PENDING']
        if started:
            self.stdout.write(self.style.WARNING(
                f"\n{len(started)} of these were part-way through the workflow:"
            ))
            for row in started[:SAMPLE_ROWS]:
                self.stdout.write(
                    f"  id={row['id']} case={row['case_id']} "
                    f"status={row['status']} region={row['region']}"
                )

        reasons = defaultdict(int)
        for _row, reason in held:
            reasons[reason] += 1
        if reasons:
            self.stdout.write("\nSTAYING OPEN")
            for reason in sorted(reasons):
                self.stdout.write(f"  {reasons[reason]:<6}{reason}")
