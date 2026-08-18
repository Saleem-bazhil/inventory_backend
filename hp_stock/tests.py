"""Regression net for the received-spare filter.

The important assertions here are the negative ones: with the setting OFF, every
HP Stock query must behave exactly as it always has.
"""
from datetime import datetime, timezone as dt_timezone
from io import StringIO

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient

# Absolute import: hp_stock is a namespace package (no __init__.py), so the test
# loader has no parent package to resolve a relative import against.
from hp_stock.models import (
    HPStockItem, HPStockSettings, OpencallActivePartCase,
    RECEIVED, IN_TRANSIT, SOURCE_MANUAL,
)

from authenticate.models import UserProfile

ITEMS = '/api/hp-stock/items/'


def make_user(username, role, region=None):
    """A user with a profile. Created explicitly: the profile signal lives in
    authenticate/signals.py but nothing imports it, so it never fires."""
    user = User.objects.create_user(username, password='x')
    UserProfile.objects.update_or_create(
        user=user, defaults={'role': role, 'region': region},
    )
    return user


class ReceivedSpareFilterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_user('admin1', 'admin')

        self.client = APIClient()
        self.client.force_authenticate(self.admin)

        # On the shelf.
        self.received = self._item('C-RECEIVED', part_received_status=RECEIVED)
        # Flex never classified it. Unknown is the resting state of every row
        # whose case has left the daily export, so it is hidden, not trusted.
        self.unknown = self._item('C-UNKNOWN')
        self.transit = self._item('C-TRANSIT', part_received_status=IN_TRANSIT)
        # In transit per Flex, but an engineer already took it: never hide.
        self.working = self._item(
            'C-WORKING', part_received_status=IN_TRANSIT, status='ISSUED',
        )
        self.closed = self._item(
            'C-CLOSED', part_received_status=IN_TRANSIT, status='CLOSED',
        )

    def _item(self, case_id, **kwargs):
        kwargs.setdefault('region', 'salem')
        kwargs.setdefault('status', 'PENDING')
        return HPStockItem.objects.create(case_id=case_id, **kwargs)

    def _toggle(self, on):
        settings_obj = HPStockSettings.load()
        settings_obj.received_spare_only = on
        settings_obj.save()  # save() also clears the cached value

    def _case_ids(self, **params):
        res = self.client.get(ITEMS, params)
        self.assertEqual(res.status_code, 200)
        return sorted(row['case_id'] for row in res.data['items'])

    # --- off: nothing changes ------------------------------------------------
    def test_off_active_tab_is_unchanged(self):
        self.assertEqual(
            self._case_ids(is_closed='false'),
            ['C-RECEIVED', 'C-TRANSIT', 'C-UNKNOWN', 'C-WORKING'],
        )

    def test_off_summary_reports_no_hidden_rows(self):
        res = self.client.get(ITEMS + 'summary/')
        self.assertEqual(res.data['in_transit_total'], 0)
        self.assertFalse(res.data['received_spare_only'])

    # --- on: anything not proven received moves -------------------------------
    def test_on_active_keeps_only_proven_received_rows(self):
        """Received, or already worked on. Unknown is not good enough."""
        self._toggle(True)
        self.assertEqual(
            self._case_ids(is_closed='false'), ['C-RECEIVED', 'C-WORKING'],
        )

    def test_on_in_transit_tab_lists_exactly_what_was_hidden(self):
        self._toggle(True)
        self.assertEqual(
            self._case_ids(is_closed='in_transit'), ['C-TRANSIT', 'C-UNKNOWN'],
        )

    def test_on_closed_tab_still_shows_closed_rows(self):
        self._toggle(True)
        self.assertEqual(self._case_ids(is_closed='true'), ['C-CLOSED'])

    def test_on_summary_counts_and_flags(self):
        self._toggle(True)
        res = self.client.get(ITEMS + 'summary/')
        self.assertEqual(res.data['in_transit_total'], 2)
        self.assertTrue(res.data['received_spare_only'])
        salem = next(r for r in res.data['regions'] if r['region'] == 'salem')
        self.assertEqual(salem['in_transit'], 2)

    # --- hand-keyed rows survive the filter -----------------------------------
    def test_row_added_through_the_form_stays_visible(self):
        """Somebody keying in a part is holding it; it must not vanish on save."""
        self._toggle(True)
        res = self.client.post(
            ITEMS, {'case_id': 'C-BYHAND', 'region': 'salem'}, format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['part_received_status'], RECEIVED)
        self.assertEqual(res.data['part_received_source'], SOURCE_MANUAL)
        self.assertIn('C-BYHAND', self._case_ids(is_closed='false'))

    def test_sync_created_row_keeps_the_blank_it_sent(self):
        """The sync sends the key explicitly, so its blank is honoured, not stamped."""
        self._toggle(True)
        res = self.client.post(
            ITEMS,
            {'case_id': 'C-SYNCED', 'region': 'salem', 'part_received_status': ''},
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['part_received_status'], '')
        self.assertNotIn('C-SYNCED', self._case_ids(is_closed='false'))
        self.assertIn('C-SYNCED', self._case_ids(is_closed='in_transit'))

    def test_on_search_still_finds_hidden_rows(self):
        """The sync locates a case's rows with ?search= and CREATES any it cannot
        see. If the filter applied here it would duplicate every hidden row on
        every cycle, so a targeted lookup must return the whole case."""
        self._toggle(True)
        self.assertEqual(self._case_ids(search='C-TRANSIT'), ['C-TRANSIT'])
        self.assertEqual(self._case_ids(search='C-UNKNOWN'), ['C-UNKNOWN'])

    def test_on_search_inside_the_in_transit_tab_still_scopes_to_hidden(self):
        """The receiving desk keeps its own meaning when someone searches it."""
        self._toggle(True)
        self.assertEqual(
            self._case_ids(is_closed='in_transit', search='C-RECEIVED'), [],
        )

    def test_on_hidden_row_is_still_reachable_by_id(self):
        """Detail routes must not 404, or the tab could not act on what it lists."""
        self._toggle(True)
        res = self.client.get('{0}{1}/'.format(ITEMS, self.transit.id))
        self.assertEqual(res.status_code, 200)

    # --- sticky ---------------------------------------------------------------
    def test_received_is_never_walked_back(self):
        res = self.client.patch(
            '{0}{1}/'.format(ITEMS, self.received.id),
            {'part_received_status': IN_TRANSIT, 'flex_installed_status': 'YTR_INTRANSIT'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.received.refresh_from_db()
        self.assertEqual(self.received.part_received_status, RECEIVED)
        # The raw Flex value is still recorded: that mismatch is the signal.
        self.assertEqual(self.received.flex_installed_status, 'YTR_INTRANSIT')

    def test_flex_can_still_promote_to_received(self):
        res = self.client.patch(
            '{0}{1}/'.format(ITEMS, self.transit.id),
            {'part_received_status': RECEIVED, 'flex_installed_status': 'RCV_SPARE'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.transit.refresh_from_db()
        self.assertEqual(self.transit.part_received_status, RECEIVED)
        self.assertIsNotNone(self.transit.part_received_at)

    # --- receiving desk -------------------------------------------------------
    def test_mark_received_makes_the_row_visible_immediately(self):
        self._toggle(True)
        res = self.client.post(
            ITEMS + 'mark_received/', {'ids': [self.transit.id]}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['updated'], 1)

        self.transit.refresh_from_db()
        self.assertEqual(self.transit.part_received_status, RECEIVED)
        self.assertEqual(self.transit.part_received_source, SOURCE_MANUAL)
        self.assertEqual(self.transit.part_received_by, self.admin)
        self.assertIn('C-TRANSIT', self._case_ids(is_closed='false'))
        # It leaves the desk; the still-unclassified row stays behind on it.
        self.assertEqual(self._case_ids(is_closed='in_transit'), ['C-UNKNOWN'])

    def test_mark_received_rejects_an_empty_payload(self):
        res = self.client.post(ITEMS + 'mark_received/', {'ids': []}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_mark_received_cannot_reach_another_region(self):
        engineer = make_user('eng1', 'engineer', region='chennai')

        client = APIClient()
        client.force_authenticate(engineer)
        res = client.post(
            ITEMS + 'mark_received/', {'ids': [self.transit.id]}, format='json',
        )
        self.assertEqual(res.data['updated'], 0)
        self.transit.refresh_from_db()
        self.assertEqual(self.transit.part_received_status, IN_TRANSIT)


class HPStockSettingsEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_user('admin2', 'admin')
        self.engineer = make_user('eng2', 'engineer', region='salem')

    def test_default_is_off(self):
        client = APIClient()
        client.force_authenticate(self.engineer)
        res = client.get('/api/hp-stock/settings/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['received_spare_only'])
        self.assertFalse(res.data['can_edit'])

    def test_admin_can_flip_it(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        res = client.patch(
            '/api/hp-stock/settings/', {'received_spare_only': True}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['received_spare_only'])
        self.assertTrue(HPStockSettings.received_only())

    def test_engineer_cannot_flip_it(self):
        client = APIClient()
        client.force_authenticate(self.engineer)
        res = client.patch(
            '/api/hp-stock/settings/', {'received_spare_only': True}, format='json',
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(HPStockSettings.received_only())


class DedupeHPStockCommandTests(TestCase):
    """The cleanup for the duplicates the blind sync created.

    Every assertion here is about what the command REFUSES to delete - that is
    the whole point of it. Losing a row an engineer worked on is far worse than
    leaving a duplicate behind for a person to look at.
    """

    def _item(self, case_id, part_order, created, **kwargs):
        kwargs.setdefault('region', 'salem')
        kwargs.setdefault('status', 'PENDING')
        item = HPStockItem.objects.create(
            case_id=case_id, part_order_number=part_order, **kwargs
        )
        # created_at is auto_now_add, so it has to be forced after the fact.
        HPStockItem.objects.filter(pk=item.pk).update(created_at=created)
        item.refresh_from_db()
        return item

    def _run(self, **opts):
        out = StringIO()
        call_command('dedupe_hp_stock', stdout=out, **opts)
        return out.getvalue()

    def setUp(self):
        self.old = datetime(2026, 8, 10, 6, 0, tzinfo=dt_timezone.utc)
        self.new = datetime(2026, 8, 18, 6, 0, tzinfo=dt_timezone.utc)

    def test_deletes_the_newer_twin_and_keeps_the_original(self):
        original = self._item('C-1', 'MO-1', self.old)
        twin = self._item('C-1', 'MO-1', self.new)

        self._run(apply=True)

        self.assertTrue(HPStockItem.objects.filter(pk=original.pk).exists())
        self.assertFalse(HPStockItem.objects.filter(pk=twin.pk).exists())

    def test_dry_run_writes_nothing(self):
        self._item('C-1', 'MO-1', self.old)
        self._item('C-1', 'MO-1', self.new)

        output = self._run()

        self.assertEqual(HPStockItem.objects.count(), 2)
        self.assertIn('DRY RUN', output)

    def test_keeps_a_duplicate_somebody_photographed(self):
        """The employee worked the twin, not the original - a person decides."""
        self._item('C-1', 'MO-1', self.old)
        worked = self._item(
            'C-1', 'MO-1', self.new,
            transition_history=[{'to_status': 'GOOD_PART_PHOTO'}],
        )

        output = self._run(apply=True)

        self.assertTrue(HPStockItem.objects.filter(pk=worked.pk).exists())
        self.assertIn('has transition history', output)

    def test_keeps_a_duplicate_past_stock_entry(self):
        self._item('C-1', 'MO-1', self.old)
        issued = self._item('C-1', 'MO-1', self.new, status='ISSUED')

        self._run(apply=True)

        self.assertTrue(HPStockItem.objects.filter(pk=issued.pk).exists())

    def test_leaves_duplicates_that_predate_the_window(self):
        self._item('C-1', 'MO-1', self.old)
        older_twin = self._item('C-1', 'MO-1', self.old)

        self._run(apply=True)

        self.assertTrue(HPStockItem.objects.filter(pk=older_twin.pk).exists())

    def test_different_parts_on_one_case_are_not_duplicates(self):
        """A multi-part case is normal - one row per part, none of them twins."""
        self._item('C-1', 'MO-1', self.old)
        self._item('C-1', 'MO-2', self.new)

        self._run(apply=True)

        self.assertEqual(HPStockItem.objects.count(), 2)

    def test_falls_back_to_good_part_number_when_there_is_no_order_number(self):
        """Part identity mirrors the sync: order number, else good part number."""
        self._item('C-1', '', self.old, good_part_number='N123-001')
        twin = self._item('C-1', '', self.new, good_part_number='N123-001')

        self._run(apply=True)

        self.assertFalse(HPStockItem.objects.filter(pk=twin.pk).exists())


class CloseStaleHPStockCommandTests(TestCase):
    """Retiring rows whose OpenCall case has finished in the field.

    As with the dedupe, the assertions that matter are the refusals: closing a
    row that is still in flight loses the fact that a part is out with someone.
    """

    REPORT_DATE = '2026-08-18'

    def _item(self, case_id, created, **kwargs):
        kwargs.setdefault('region', 'salem')
        kwargs.setdefault('status', 'PENDING')
        item = HPStockItem.objects.create(case_id=case_id, **kwargs)
        HPStockItem.objects.filter(pk=item.pk).update(
            created_at=created, case_created_time=created,
        )
        item.refresh_from_db()
        return item

    def _active(self, *case_ids):
        for case_id in case_ids:
            OpencallActivePartCase.objects.create(
                report_date=self.REPORT_DATE, case_id=case_id, region='salem',
            )

    def _run(self, **opts):
        out = StringIO()
        call_command('close_stale_hp_stock', stdout=out, **opts)
        return out.getvalue()

    def setUp(self):
        self.old = datetime(2026, 6, 1, 6, 0, tzinfo=dt_timezone.utc)
        self.recent = timezone.now()

    def test_closes_a_row_whose_case_left_the_active_list(self):
        self._active('C-LIVE')
        stale = self._item('C-GONE', self.old)

        self._run(apply=True)

        stale.refresh_from_db()
        self.assertEqual(stale.status, 'CLOSED')

    def test_writes_an_audit_trail_entry(self):
        self._active('C-LIVE')
        stale = self._item('C-GONE', self.old)

        self._run(apply=True)

        stale.refresh_from_db()
        entry = stale.transition_history[-1]
        self.assertEqual(entry['from_status'], 'PENDING')
        self.assertEqual(entry['to_status'], 'CLOSED')
        self.assertIn('no longer active', entry['comment'])

    def test_dry_run_writes_nothing(self):
        self._active('C-LIVE')
        stale = self._item('C-GONE', self.old)

        output = self._run()

        stale.refresh_from_db()
        self.assertEqual(stale.status, 'PENDING')
        self.assertIn('DRY RUN', output)

    def test_keeps_a_row_whose_case_is_still_active(self):
        self._active('C-LIVE')
        live = self._item('C-LIVE', self.old)

        self._run(apply=True)

        live.refresh_from_db()
        self.assertEqual(live.status, 'PENDING')

    def test_keeps_a_part_still_out_with_an_engineer(self):
        """Closing this would erase the fact that somebody is holding the part."""
        self._active('C-LIVE')
        issued = self._item('C-GONE', self.old, status='ISSUED')

        output = self._run(apply=True)

        issued.refresh_from_db()
        self.assertEqual(issued.status, 'ISSUED')
        self.assertIn('still out with an engineer', output)

    def test_keeps_a_row_inside_the_grace_period(self):
        self._active('C-LIVE')
        fresh = self._item('C-GONE', self.recent)

        self._run(apply=True)

        fresh.refresh_from_db()
        self.assertEqual(fresh.status, 'PENDING')

    def test_keeps_a_part_received_but_never_issued(self):
        """Somebody handled this spare and no engineer took it - it is on a shelf."""
        self._active('C-LIVE')
        on_shelf = self._item('C-GONE', self.old, status='GOOD_PART_PHOTO')

        output = self._run(apply=True)

        on_shelf.refresh_from_db()
        self.assertEqual(on_shelf.status, 'GOOD_PART_PHOTO')
        self.assertIn('received but never issued', output)

    def test_include_in_stock_closes_them_anyway(self):
        self._active('C-LIVE')
        on_shelf = self._item('C-GONE', self.old, status='STOCK_CHECK')

        self._run(apply=True, include_in_stock=True)

        on_shelf.refresh_from_db()
        self.assertEqual(on_shelf.status, 'CLOSED')

    def test_closes_a_part_the_engineer_already_handed_back(self):
        """Past HANDOVER the part is back in the building - nothing is in flight."""
        self._active('C-LIVE')
        returned = self._item('C-GONE', self.old, status='RETURN_PART_PHOTO')

        self._run(apply=True)

        returned.refresh_from_db()
        self.assertEqual(returned.status, 'CLOSED')

    def test_refuses_to_run_without_an_active_case_list(self):
        """No list means "we were not told", not "nothing is active"."""
        self._item('C-GONE', self.old)

        with self.assertRaises(CommandError):
            self._run(apply=True)

        self.assertEqual(HPStockItem.objects.get(case_id='C-GONE').status, 'PENDING')
