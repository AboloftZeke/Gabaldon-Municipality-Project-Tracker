from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase


class PhilippineTimeDisplayTests(SimpleTestCase):
    def test_utc_timestamp_crossing_midnight_displays_next_manila_day(self):
        timestamp = datetime(
            2026,
            9,
            13,
            16,
            35,
            tzinfo=datetime_timezone.utc,
        )

        rendered = Template(
            '{{ timestamp|date:"M d, Y g:i A" }}',
        ).render(Context({'timestamp': timestamp}, use_tz=True))

        self.assertEqual(settings.TIME_ZONE, 'Asia/Manila')
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(rendered, 'Sep 14, 2026 12:35 AM')
