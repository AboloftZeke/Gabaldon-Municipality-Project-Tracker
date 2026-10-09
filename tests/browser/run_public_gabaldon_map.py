"""Run optional Chromium checks against a disposable DB and development server."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix='gabaldon-map-browser-') as temporary:
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'
        os.environ['TEST_DATABASE_PATH'] = str(Path(temporary) / 'database.sqlite3')
        import django
        django.setup()
        from django.core.management import call_command
        from apps.system.tests import (
            PublicDashboardInfrastructureDataSourceTests,
            PublicDashboardNonInfrastructureStatusTests,
        )
        call_command('migrate', interactive=False, verbosity=0)
        # Reuse the publication-aware fixtures from the existing public tests.
        PublicDashboardInfrastructureDataSourceTests().setUp()
        PublicDashboardNonInfrastructureStatusTests().setUp()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        base_url = f'http://127.0.0.1:{port}'
        with (Path(temporary) / 'server.log').open('w+') as log:
            server = subprocess.Popen([
                sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}',
                '--settings=config.test_settings', '--noreload',
            ], cwd=ROOT, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        with urlopen(base_url + '/login/', timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError('Test server did not become ready')
                subprocess.run([
                    'node', str(ROOT / 'tests/browser/check_public_gabaldon_map.cjs'),
                ], cwd=ROOT, env={**os.environ, 'BASE_URL': base_url}, check=True)
                subprocess.run([
                    'node', str(ROOT / 'tests/browser/check_project_detail_gis.cjs'),
                ], cwd=ROOT, env={**os.environ, 'BASE_URL': base_url}, check=True)
                from apps.infrastructure.tests import InfrastructureProjectFormTests
                from apps.system.models import UserRole
                from django.test import Client
                from django.urls import reverse
                fixture = InfrastructureProjectFormTests()
                fixture.setUp()
                fixture.user.is_staff = True
                fixture.user.save(update_fields=['is_staff'])
                UserRole.objects.update_or_create(
                    user=fixture.user, defaults={'department': 'engineer', 'role': 'staff'},
                )
                saved = fixture.create_project(latitude='15.4541234', longitude='121.3375123')
                missing = fixture.create_project(title='Site not yet confirmed')
                missing.address.latitude = missing.address.longitude = None
                missing.address.save(update_fields=['latitude', 'longitude'])
                client = Client()
                client.force_login(fixture.user)
                subprocess.run([
                    'node', str(ROOT / 'tests/browser/check_infrastructure_location_picker.cjs'),
                ], cwd=ROOT, env={
                    **os.environ, 'BASE_URL': base_url,
                    'PICKER_SESSION': client.cookies['sessionid'].value,
                    'PICKER_CREATE_PATH': reverse('engineering_projects:project_create'),
                    'PICKER_EDIT_PATH': reverse('engineering_projects:project_update', args=[saved.pk]),
                    'PICKER_MISSING_PATH': reverse('engineering_projects:project_update', args=[missing.pk]),
                }, check=True)
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    main()
