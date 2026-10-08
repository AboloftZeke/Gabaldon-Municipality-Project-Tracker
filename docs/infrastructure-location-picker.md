The Infrastructure create/edit wizard now selects a site through the map in
the Location step. Click to place one marker, click elsewhere to replace it, or
drag it to adjust the site. Read-only coordinate outputs confirm the selection;
hidden latitude/longitude inputs submit seven decimal places to the existing
InfrastructureProjectForm and Address save logic. Editing loads the saved point
at zoom 16. New records and legacy records without coordinates start with no
marker at Gabaldon's GeoNames town center (15.4522, 121.3387), zoom 12.

Coordinates remain required for create/edit saves, matching the existing form
requirement. No new publication-readiness gate is introduced, and the Staff →
Head Review → Publish workflow stays unchanged. A legacy record without a point
can still be opened; Staff must select a point before saving it through this
form. Hidden fields are validated on the server, including numeric/finite
values, geographic ranges, and the existing seven-decimal-place precision.

There is no local trustworthy municipal polygon. The bundled barangay/road
layers are labeled placeholders; the live GeoRisk barangay service is not a
retained verified boundary dataset. The picker does not fabricate a bounding
box, pan to invented barangay locations, or claim municipality containment
validation. Global coordinate ranges are enforced; Staff still need to select
the correct Gabaldon site. This limitation can be addressed separately once a
verified local polygon is supplied.

The picker reuses local Leaflet 1.9.4 assets and online OpenStreetMap tiles.
It initializes when the wizard's Location step becomes visible and recalculates
its size on step changes and container/window resizing. It does not change the
public Gabaldon exploration map, project-detail maps, publication snapshots,
location endpoints, or database schema.

Targeted checks:

```sh
venv/bin/python manage.py test apps.infrastructure.test_location_picker \
  apps.infrastructure.tests apps.infrastructure.test_inspections \
  apps.system.test_public_gabaldon_map \
  apps.system.tests.PublicDashboardInfrastructureDataSourceTests \
  apps.system.tests.PublicDashboardNonInfrastructureStatusTests \
  --settings=config.test_settings --noinput
```

Browser interaction checks run with the public-map browser runner; see
`tests/browser/README.md` for Playwright/Chromium prerequisites.
