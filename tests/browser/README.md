Public Gabaldon map browser regression checks use an isolated SQLite database,
published fixtures from the existing public-view tests, and a temporary Django
server. They leave the development database untouched.

Install Playwright in a directory outside the repository, install its Chromium
browser, and make the Node package available through NODE_PATH. Then run:

```sh
NODE_PATH=/path/to/node_modules venv/bin/python tests/browser/run_public_gabaldon_map.py
```

If using a system Chromium, set `CHROMIUM_EXECUTABLE=/usr/bin/chromium`.
The checks use deterministic image tile fixtures to verify real Leaflet tile
positioning, desktop/mobile controls, pan/zoom, registry filtering independence,
and tile outage recovery. They do not verify live OpenStreetMap availability.

For Django public dashboard, detail and GIS API regressions:

```sh
venv/bin/python manage.py test apps.system.test_public_gabaldon_map \
  apps.system.tests.PublicDashboardInfrastructureDataSourceTests \
  apps.system.tests.PublicDashboardNonInfrastructureStatusTests \
  --settings=config.test_settings --noinput
```
