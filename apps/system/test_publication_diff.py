from django.test import SimpleTestCase

from .publication_diff import compare_snapshots


class SnapshotDiffTests(SimpleTestCase):
    def rows(self, before, after, section='infrastructure'):
        result = compare_snapshots({section: after}, {section: before})
        return {row['path']: row for row in result['sections'][0]['fields']}

    def test_initial_submission_has_no_fake_changes(self):
        result = compare_snapshots({'infrastructure': {'title': 'New'}, 'images': [{'id': 1, 'url': '/one.jpg'}]})
        self.assertEqual(result['change_count'], 0)

    def test_field_change_states(self):
        rows = self.rows(
            {'title': 'Old', 'description': 'Clear me', 'code': 'Same'},
            {'title': 'New', 'description': '', 'code': 'Same', 'procurement_method': 'bidding'},
        )
        self.assertEqual(rows['title']['state'], 'modified')
        self.assertEqual(rows['title']['before'], 'Old')
        self.assertEqual(rows['title']['after'], 'New')
        self.assertEqual(rows['description']['state'], 'removed')
        self.assertEqual(rows['code']['state'], 'unchanged')
        self.assertEqual(rows['procurement_method']['state'], 'added')

    def test_null_missing_and_empty_are_equivalent_but_zero_is_a_value(self):
        rows = self.rows({'description': None, 'beneficiaries': None}, {'description': '', 'beneficiaries': 0}, 'non_infrastructure')
        self.assertEqual(rows['description']['state'], 'unchanged')
        self.assertEqual(rows['beneficiaries']['state'], 'added')
        self.assertEqual(rows['beneficiaries']['after'], '0')

    def test_infrastructure_nested_values_and_metadata(self):
        rows = self.rows(
            {'id': 1, 'updated_at': 'old', 'address': {'id': 1, 'street': 'Old'}, 'physical_progress_percentage': '10.00'},
            {'id': 2, 'updated_at': 'new', 'address': {'id': 2, 'street': 'New'}, 'physical_progress_percentage': '10'},
        )
        self.assertEqual(set(rows), {'address.street', 'physical_progress_percentage'})
        self.assertTrue(rows['address.street']['changed'])
        self.assertFalse(rows['physical_progress_percentage']['changed'])

    def test_removed_nested_section_and_named_relationship(self):
        rows = self.rows({'address': {'street': 'Old'}, 'category': {'id': 1, 'name': 'Road'}}, {'address': None, 'category': None})
        self.assertEqual(rows['address.street']['state'], 'removed')
        self.assertEqual(rows['category']['before'], 'Road')
        self.assertEqual(rows['category']['state'], 'removed')

    def test_non_infrastructure_event_and_status(self):
        rows = self.rows({'event_date': '2026-09-01', 'status': 'planned', 'status_label': 'Planned'}, {'event_date': '2026-09-02', 'status': 'completed', 'status_label': 'Completed'}, 'non_infrastructure')
        self.assertEqual(rows['event_date']['state'], 'modified')
        self.assertEqual(rows['status']['after'], 'Completed')
        self.assertNotIn('status_label', rows)

    def test_images_added_removed_and_cover_changed(self):
        old = {'images': [{'id': 1, 'url': '/1', 'is_cover': True}, {'id': 2, 'url': '/2'}]}
        new = {'images': [{'id': 1, 'url': '/1', 'is_cover': False}, {'id': 3, 'url': '/3'}]}
        result = compare_snapshots(new, old)
        self.assertEqual([row['state'] for row in result['images']], ['modified', 'added', 'removed'])

    def test_image_order_and_capture_time_do_not_count_as_changes(self):
        old = {'images': [{'url': '/1', 'created_at': 'old'}, {'id': 2, 'url': '/2'}]}
        new = {'images': [{'id': 2, 'url': '/2'}, {'url': '/1', 'created_at': 'new'}]}
        self.assertEqual(compare_snapshots(new, old)['change_count'], 0)
