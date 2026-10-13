# Infrastructure location picker

Infrastructure project creation and editing use the Leaflet map picker to set
the exact site coordinates. Selecting a point or dragging the marker updates
the existing hidden latitude and longitude form fields; the Infrastructure
form continues to persist those values to the normalized `Address` record.

The wizard validates that a point is selected before leaving the Location
step, and the backend still validates coordinate presence, numeric precision,
and geographic range. Existing coordinates open with their marker in place.
The basemap uses OpenStreetMap tiles, so the selected coordinates can be saved
even if tile loading is temporarily unavailable.
