document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  const picker = document.querySelector("[data-location-picker]");
  if (!picker) return;
  const container = picker.querySelector("[data-location-map]");
  const panel = picker.closest("[data-wizard-step]");
  const latitude = picker.querySelector('[name="latitude"]');
  const longitude = picker.querySelector('[name="longitude"]');
  const latitudeDisplay = picker.querySelector("[data-selected-latitude]");
  const longitudeDisplay = picker.querySelector("[data-selected-longitude]");
  const clearButton = picker.querySelector("[data-clear-location]");
  const error = picker.querySelector("[data-location-error]");
  const tileStatus = picker.querySelector("[data-location-map-status]");
  let map, marker, pendingResize;

  function selectedPoint() {
    if (!latitude.value.trim() || !longitude.value.trim()) return null;
    const lat = Number(latitude.value), lng = Number(longitude.value);
    return Number.isFinite(lat) && Number.isFinite(lng) &&
      lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180 ? [lat, lng] : null;
  }

  function updateDisplay() {
    const point = selectedPoint();
    latitudeDisplay.textContent = point ? point[0].toFixed(7) : "Not selected";
    longitudeDisplay.textContent = point ? point[1].toFixed(7) : "Not selected";
    clearButton.disabled = !point;
  }

  function setPoint(point) {
    latitude.value = point ? point.lat.toFixed(7) : "";
    longitude.value = point ? point.lng.toFixed(7) : "";
    for (const field of [latitude, longitude]) {
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }
    error.hidden = true;
    container.removeAttribute("aria-invalid");
    picker.classList.remove("has-client-error", "has-error");
    const serverErrors = picker.querySelector("[data-location-server-errors]");
    if (serverErrors) serverErrors.hidden = true;
    updateDisplay();
  }

  function placeMarker(point) {
    if (marker) marker.setLatLng(point);
    else {
      marker = L.marker(point, { draggable: true, title: "Selected project location" }).addTo(map);
      marker.on("dragend", () => {
        const moved = marker.getLatLng().wrap();
        marker.setLatLng(moved);
        setPoint(moved);
      });
    }
  }

  function resizeMap() {
    cancelAnimationFrame(pendingResize);
    pendingResize = requestAnimationFrame(() => {
      // The wizard initially hides this step. Initialize only when visible.
      if (!container.clientWidth || !container.clientHeight) return;
      if (!map) {
        if (!window.L) {
          tileStatus.textContent = "The map could not be loaded. Reload the page to select a location.";
          tileStatus.hidden = false;
          return;
        }
        const saved = selectedPoint();
        // Same verified GeoNames Gabaldon town center as the public map.
        map = L.map(container).setView(saved || [15.4522, 121.3387], saved ? 16 : 12);
        const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        });
        let loaded = 0;
        tiles.on("loading", () => { loaded = 0; });
        tiles.on("tileload", () => { loaded += 1; });
        tiles.on("load", () => {
          tileStatus.textContent = "Map tiles are unavailable. Check your connection before choosing the exact site.";
          tileStatus.hidden = loaded > 0;
        });
        tiles.addTo(map);
        L.control.scale({ imperial: false }).addTo(map);
        if (saved) placeMarker(saved);
        map.on("click", event => {
          const point = event.latlng.wrap();
          placeMarker(point);
          setPoint(point);
        });
      }
      map.invalidateSize({ pan: false });
    });
  }

  clearButton.addEventListener("click", () => {
    if (marker) map.removeLayer(marker);
    marker = null;
    setPoint(null);
  });
  picker.addEventListener("location-picker:validate", event => {
    if (selectedPoint()) return;
    event.preventDefault();
    error.textContent = "Select the exact project location on the map before continuing.";
    error.hidden = false;
    container.setAttribute("aria-invalid", "true");
    picker.classList.add("has-client-error");
    container.focus();
  });
  if (window.ResizeObserver) new ResizeObserver(resizeMap).observe(container);
  if (panel) new MutationObserver(resizeMap).observe(panel, { attributes: true, attributeFilter: ["hidden"] });
  window.addEventListener("resize", resizeMap);
  updateDisplay();
  resizeMap();
});
