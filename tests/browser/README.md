Public Gabaldon map and Infrastructure location-picker browser regression checks
use an isolated SQLite database, existing public/form fixtures, and a temporary
Django server. They leave the development database untouched. The picker tests
authenticate an Engineering Staff session only within that disposable database.

Install Playwright in a directory outside the repository, install its Chromium
browser, and make the Node package available through NODE_PATH. Then run:

```sh
NODE_PATH=/path/to/node_modules venv/bin/python tests/browser/run_public_gabaldon_map.py
```

If using a system Chromium, set `CHROMIUM_EXECUTABLE=/usr/bin/chromium`.
The checks use deterministic image tile fixtures to verify real Leaflet tile
positioning, desktop/mobile controls, pan/zoom, registry filtering independence,
and tile outage recovery. Picker checks also cover one-marker selection, drag,
replacement, clearing, hidden coordinates, required-location validation, saved
edit markers, and wizard step resizing. They do not verify live OpenStreetMap
availability.

For Django public dashboard, detail and GIS API regressions:

```sh
venv/bin/python manage.py test apps.system.test_public_gabaldon_map \
  apps.system.tests.PublicDashboardInfrastructureDataSourceTests \
  apps.system.tests.PublicDashboardNonInfrastructureStatusTests \
  --settings=config.test_settings --noinput
```
