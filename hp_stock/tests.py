"""Regression net for the received-spare filter.

The important assertions here are the negative ones: with the setting OFF, every
HP Stock query must behave exactly as it always has.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

# Absolute import: hp_stock is a namespace package (no __init__.py), so the test
# loader has no parent package to resolve a relative import against.
from hp_stock.models import (
    HPStockItem, HPStockSettings, RECEIVED, IN_TRANSIT, SOURCE_MANUAL,
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
        # Flex never classified it: unknown is not evidence of absence.
        self.unknown = self._item('C-UNKNOWN')
        # The only row the filter should hide.
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

    # --- on: exactly one row moves -------------------------------------------
    def test_on_hides_only_the_in_transit_row(self):
        self._toggle(True)
        self.assertEqual(
            self._case_ids(is_closed='false'),
            ['C-RECEIVED', 'C-UNKNOWN', 'C-WORKING'],
        )

    def test_on_in_transit_tab_lists_exactly_what_was_hidden(self):
        self._toggle(True)
        self.assertEqual(self._case_ids(is_closed='in_transit'), ['C-TRANSIT'])

    def test_on_closed_tab_still_shows_closed_rows(self):
        self._toggle(True)
        self.assertEqual(self._case_ids(is_closed='true'), ['C-CLOSED'])

    def test_on_summary_counts_and_flags(self):
        self._toggle(True)
        res = self.client.get(ITEMS + 'summary/')
        self.assertEqual(res.data['in_transit_total'], 1)
        self.assertTrue(res.data['received_spare_only'])
        salem = next(r for r in res.data['regions'] if r['region'] == 'salem')
        self.assertEqual(salem['in_transit'], 1)

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
        self.assertEqual(self._case_ids(is_closed='in_transit'), [])

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
