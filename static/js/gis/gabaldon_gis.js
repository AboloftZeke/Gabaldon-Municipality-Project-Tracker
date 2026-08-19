/**
 * Gabaldon Municipal GIS
 * Integrates into an existing Django project-detail/dashboard page.
 * Expects the markup + data-api-* attributes from
 * templates/projects/project_detail_gis_section.html.
 */
(function () {
  "use strict";

  const root = document.getElementById("gabaldon-gis-root");
  if (!root) return; // section not present on this page — do nothing

  const API = {
    barangays: root.dataset.apiBarangays,
    roads: root.dataset.apiRoads,
    bridges: root.dataset.apiBridges,
    waterways: root.dataset.apiWaterways,
    facilities: root.dataset.apiFacilities,
    projects: root.dataset.apiProjects,
    photosTemplate: root.dataset.apiPhotosTemplate,
  };

  const STATUS_COLORS = {
    completed: "#2ecc71",
    ongoing: "#3498db",
    planned: "#f1c40f",
    delayed: "#e74c3c",
    unknown: "#95a5a6",
  };

  const FACILITY_ICONS = {
    School: "🏫",
    "Barangay Hall": "🏛",
    "Municipal Hall": "🏛",
    "Health Center": "🏥",
    Hospital: "🏥",
    Clinic: "🏥",
    "Police Station": "🚓",
    "Fire Station": "🚒",
    "Evacuation Center": "🏠",
    Church: "⛪",
    "Public Market": "🛒",
    "Government Office": "🏛",
    Park: "🌳",
    Other: "📍",
  };

  // ---------------------------------------------------------------
  // Map init
  // ---------------------------------------------------------------
  const GABALDON_CENTER = [15.365, 121.16]; // approx municipality center; adjust once real boundary data is loaded
  const focusProjectId = (root.dataset.focusProjectId || "").trim();
  const focusProjectType = (root.dataset.focusProjectType || "").trim();
  const focusLat = Number.parseFloat(root.dataset.focusLat);
  const focusLng = Number.parseFloat(root.dataset.focusLng);
  const hasFocusCoordinates = Number.isFinite(focusLat) && Number.isFinite(focusLng);
  const map = L.map("gabaldon-gis-map", { zoomControl: true }).setView(
    hasFocusCoordinates ? [focusLat, focusLng] : GABALDON_CENTER,
    hasFocusCoordinates ? 16 : 13
  );

  const osmTiles = L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
    }
  );
  osmTiles.addTo(map);

  // Fallback: if OSM tiles fail to load (offline, blocked, rate-limited),
  // fall back to a plain background and tell the user — never fabricate a
  // fake grid and pass it off as a real basemap.
  let tileErrorShown = false;
  osmTiles.on("tileerror", function () {
    if (tileErrorShown) return;
    tileErrorShown = true;
    document.getElementById("gis-tile-fallback-banner").hidden = false;
    document.getElementById("gabaldon-gis-map").classList.add("gis-no-basemap");
  });

  // NOTE: to switch to self-hosted tiles once available, replace the
  // tileLayer URL above with your own, e.g.
  //   L.tileLayer('/static/tiles/{z}/{x}/{y}.png', { maxZoom: 18 })
  // Everything else in this file is unaffected by that change.

  // ---------------------------------------------------------------
  // Layer groups
  // ---------------------------------------------------------------
  const layers = {
    barangays: L.layerGroup(),
    roads: L.layerGroup(),
    bridges: L.layerGroup(),
    waterways: L.layerGroup(),
    facilities: L.layerGroup(),
    projectsInfra: L.markerClusterGroup({ maxClusterRadius: 45 }),
    projectsNonInfra: L.markerClusterGroup({ maxClusterRadius: 45 }),
  };
  Object.values(layers).forEach((l) => l.addTo(map));

  L.control
    .layers(
      null,
      {
        "Barangay Boundaries": layers.barangays,
        Roads: layers.roads,
        Bridges: layers.bridges,
        "Rivers / Waterways": layers.waterways,
        "Public Facilities": layers.facilities,
        "Infrastructure Projects": layers.projectsInfra,
        "Non-Infrastructure Projects": layers.projectsNonInfra,
      },
      { collapsed: false }
    )
    .addTo(map);

  // Keep references to raw GeoJSON layers (not the clusters) for search/filter
  let barangayLayer = null;
  let allBarangayNames = [];
  let projectFeaturesCache = []; // last-fetched project GeoJSON features
  const projectMarkersByKey = new Map();

  // ---------------------------------------------------------------
  // Fetch helper
  // ---------------------------------------------------------------
  async function fetchGeoJSON(url) {
    if (!url) return { type: "FeatureCollection", features: [] };
    try {
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error("HTTP " + res.status);
      return await res.json();
    } catch (err) {
      console.error("GIS layer failed to load:", url, err);
      return { type: "FeatureCollection", features: [], _error: true };
    }
  }

  // ---------------------------------------------------------------
  // Barangay boundaries
  // ---------------------------------------------------------------
  function styleBarangay() {
    return { color: "#2c3e50", weight: 2, fillColor: "#3498db", fillOpacity: 0.08 };
  }
  function styleBarangayHover() {
    return { fillOpacity: 0.25, weight: 3 };
  }

  async function loadBarangays() {
    const data = await fetchGeoJSON(API.barangays);
    barangayLayer = L.geoJSON(data, {
      style: styleBarangay,
      onEachFeature: function (feature, layer) {
        const name = feature.properties.name || "Unknown barangay";
        allBarangayNames.push(name);

        layer.on("mouseover", () => layer.setStyle(styleBarangayHover()));
        layer.on("mouseout", () => layer.setStyle(styleBarangay()));
        layer.on("click", () => {
          highlightBarangay(name);
          showBarangayPopup(layer, feature);
        });
      },
    });
    layers.barangays.addLayer(barangayLayer);

    populateBarangayDropdown([...new Set(allBarangayNames)].sort());
  }

  function showBarangayPopup(layer, feature) {
    const name = feature.properties.name || "Unknown";
    const placeholderNote = feature.properties.is_placeholder
      ? '<div class="gis-placeholder-note">Placeholder boundary — not real data</div>'
      : "";
    const inBarangay = projectFeaturesCache.filter((f) => f.properties.barangay === name);
    const infra = inBarangay.filter((f) => f.properties.type === "infrastructure").length;
    const nonInfra = inBarangay.filter((f) => f.properties.type === "non_infrastructure").length;

    const html = `
      <div class="gis-popup">
        <h4>${escapeHtml(name)}</h4>
        <table>
          <tr><td>Municipality</td><td>Gabaldon</td></tr>
          <tr><td>Province</td><td>Nueva Ecija</td></tr>
          <tr><td>Projects</td><td>${inBarangay.length}</td></tr>
          <tr><td>Infrastructure</td><td>${infra}</td></tr>
          <tr><td>Non-Infrastructure</td><td>${nonInfra}</td></tr>
        </table>
        ${placeholderNote}
      </div>`;
    layer.bindPopup(html).openPopup();
  }

  function highlightBarangay(name) {
    if (!barangayLayer) return;
    barangayLayer.eachLayer((l) => {
      if (l.feature.properties.name === name) {
        l.setStyle({ color: "#e67e22", weight: 4, fillOpacity: 0.3 });
        map.fitBounds(l.getBounds(), { maxZoom: 16 });
      } else {
        l.setStyle(styleBarangay());
      }
    });
  }

  // ---------------------------------------------------------------
  // Roads
  // ---------------------------------------------------------------
  async function loadRoads() {
    const data = await fetchGeoJSON(API.roads);
    L.geoJSON(data, {
      style: { color: "#7f8c8d", weight: 3 },
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};
        layer.bindPopup(`
          <div class="gis-popup">
            <h4>${escapeHtml(p.name || "Unnamed road")}</h4>
            <table>
              <tr><td>Type</td><td>${escapeHtml(p.road_type || "—")}</td></tr>
              <tr><td>Barangay</td><td>${escapeHtml(p.barangay || "—")}</td></tr>
              <tr><td>Condition</td><td>${escapeHtml(p.condition || "—")}</td></tr>
            </table>
            ${p.is_placeholder ? '<div class="gis-placeholder-note">Placeholder road — not real data</div>' : ""}
          </div>`);
      },
    }).addTo(layers.roads);
  }

  // ---------------------------------------------------------------
  // Bridges
  // ---------------------------------------------------------------
  const bridgeIcon = L.divIcon({ html: "🌉", className: "gis-emoji-icon", iconSize: [24, 24] });

  async function loadBridges() {
    const data = await fetchGeoJSON(API.bridges);
    L.geoJSON(data, {
      pointToLayer: (feature, latlng) => L.marker(latlng, { icon: bridgeIcon }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};
        layer.bindPopup(`
          <div class="gis-popup">
            <h4>🌉 ${escapeHtml(p.name || "Unnamed bridge")}</h4>
            <table>
              <tr><td>Type</td><td>${escapeHtml(p.bridge_type || "—")}</td></tr>
              <tr><td>Barangay</td><td>${escapeHtml(p.barangay || "—")}</td></tr>
              <tr><td>Condition</td><td>${escapeHtml(p.condition || "—")}</td></tr>
            </table>
            ${p.is_placeholder ? '<div class="gis-placeholder-note">Placeholder bridge — not real data</div>' : ""}
          </div>`);
      },
    }).addTo(layers.bridges);
  }

  // ---------------------------------------------------------------
  // Waterways
  // ---------------------------------------------------------------
  async function loadWaterways() {
    const data = await fetchGeoJSON(API.waterways);
    L.geoJSON(data, {
      style: { color: "#2980b9", weight: 2, dashArray: "4 3" },
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};
        layer.bindPopup(`
          <div class="gis-popup">
            <h4>💧 ${escapeHtml(p.name || "Unnamed waterway")}</h4>
            <table>
              <tr><td>Type</td><td>${escapeHtml(p.waterway_type || "—")}</td></tr>
              <tr><td>Barangay</td><td>${escapeHtml(p.barangay || "—")}</td></tr>
            </table>
            ${p.is_placeholder ? '<div class="gis-placeholder-note">Placeholder waterway — not real data</div>' : ""}
          </div>`);
      },
    }).addTo(layers.waterways);
  }

  // ---------------------------------------------------------------
  // Facilities
  // ---------------------------------------------------------------
  function facilityIcon(type) {
    const emoji = FACILITY_ICONS[type] || FACILITY_ICONS.Other;
    return L.divIcon({ html: emoji, className: "gis-emoji-icon", iconSize: [24, 24] });
  }

  async function loadFacilities() {
    const data = await fetchGeoJSON(API.facilities);
    L.geoJSON(data, {
      pointToLayer: (feature, latlng) => L.marker(latlng, { icon: facilityIcon(feature.properties.type) }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};
        layer.bindPopup(`
          <div class="gis-popup">
            <h4>${FACILITY_ICONS[p.type] || "📍"} ${escapeHtml(p.name || "Unnamed facility")}</h4>
            <table>
              <tr><td>Type</td><td>${escapeHtml(p.type || "—")}</td></tr>
              <tr><td>Barangay</td><td>${escapeHtml(p.barangay || "—")}</td></tr>
            </table>
            <p>${escapeHtml(p.description || "")}</p>
            ${p.is_placeholder ? '<div class="gis-placeholder-note">Placeholder facility — not real data</div>' : ""}
          </div>`);
      },
    }).addTo(layers.facilities);
  }

  // ---------------------------------------------------------------
  // Projects (dynamic layer, filterable, clustered)
  // ---------------------------------------------------------------
  function projectMarkerIcon(props) {
    const color = STATUS_COLORS[props.status_key] || STATUS_COLORS.unknown;
    const glyph = props.type === "infrastructure" ? "🏗" : "📋";
    return L.divIcon({
      html: `<span class="gis-project-marker" style="background:${color}">${glyph}</span>`,
      className: "",
      iconSize: [28, 28],
    });
  }

  function projectPopupHtml(props) {
    return `
      <div class="gis-popup gis-popup-project">
        <h4>${escapeHtml(props.name || "Untitled project")}</h4>
        <table>
          <tr><td>Code</td><td>${escapeHtml(props.code || "—")}</td></tr>
          <tr><td>Type</td><td>${props.type === "infrastructure" ? "Infrastructure" : "Non-Infrastructure"}</td></tr>
          <tr><td>Status</td><td>${escapeHtml(props.status || "—")}</td></tr>
          <tr><td>Progress</td><td>${props.progress != null ? props.progress + "%" : "—"}</td></tr>
          <tr><td>Budget</td><td>${props.budget != null ? escapeHtml(String(props.budget)) : "—"}</td></tr>
          <tr><td>Funding Source</td><td>${escapeHtml(props.funding_source || "—")}</td></tr>
          <tr><td>Implementing Office</td><td>${escapeHtml(props.implementing_office || "—")}</td></tr>
          <tr><td>Barangay</td><td>${escapeHtml(props.barangay || "—")}</td></tr>
          <tr><td>Location</td><td>${escapeHtml(props.address || "—")}</td></tr>
        </table>
        <div class="gis-popup-photos" id="gis-photos-${props.project_id}">Loading photos…</div>
        <a class="gis-btn gis-popup-link" href="${props.detail_url}">View Full Project Details</a>
      </div>`;
  }

  function loadPhotosForPopup(projectId) {
    const container = document.getElementById(`gis-photos-${projectId}`);
    if (!container || !API.photosTemplate) return;
    const url = API.photosTemplate.replace("__ID__", projectId);
    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (!data.photos || !data.photos.length) {
          container.innerHTML = "";
          return;
        }
        container.innerHTML = data.photos
          .slice(0, 6)
          .map((p) => `<img src="${p.url}" alt="${escapeHtml(p.caption || "")}" class="gis-thumb" data-full="${p.url}">`)
          .join("");
        container.querySelectorAll(".gis-thumb").forEach((img) => {
          img.addEventListener("click", () => openLightbox(img.dataset.full));
        });
      })
      .catch(() => {
        container.innerHTML = "";
      });
  }

  async function loadProjects(filters) {
    const params = new URLSearchParams(filters || {});
    const url = API.projects + (params.toString() ? "?" + params.toString() : "");
    const data = await fetchGeoJSON(url);
    projectFeaturesCache = data.features || [];

    layers.projectsInfra.clearLayers();
    layers.projectsNonInfra.clearLayers();
    projectMarkersByKey.clear();

    projectFeaturesCache.forEach((feature) => {
      const [lng, lat] = feature.geometry.coordinates;
      const props = feature.properties;
      const marker = L.marker([lat, lng], { icon: projectMarkerIcon(props) });
      marker.bindPopup(() => projectPopupHtml(props));
      marker.on("popupopen", () => loadPhotosForPopup(props.project_id));

      if (props.type === "infrastructure") {
        layers.projectsInfra.addLayer(marker);
      } else {
        layers.projectsNonInfra.addLayer(marker);
      }
      projectMarkersByKey.set(`${props.type}:${props.project_id}`, marker);
    });

    updateStats(projectFeaturesCache);
  }

  function focusConfiguredProject() {
    if (!focusProjectId || !focusProjectType) return;

    const marker = projectMarkersByKey.get(
      `${focusProjectType}:${focusProjectId}`
    );

    if (!marker) {
      if (hasFocusCoordinates) map.setView([focusLat, focusLng], 16);
      return;
    }

    const cluster = focusProjectType === "infrastructure"
      ? layers.projectsInfra
      : layers.projectsNonInfra;

    cluster.zoomToShowLayer(marker, () => {
      map.setView(marker.getLatLng(), Math.max(map.getZoom(), 16));
      marker.openPopup();
    });
  }

  function updateStats(features) {
    const total = features.length;
    const infra = features.filter((f) => f.properties.type === "infrastructure").length;
    const nonInfra = total - infra;
    const byStatus = (key) => features.filter((f) => f.properties.status_key === key).length;

    document.getElementById("stat-total").textContent = total;
    document.getElementById("stat-infra").textContent = infra;
    document.getElementById("stat-noninfra").textContent = nonInfra;
    document.getElementById("stat-ongoing").textContent = byStatus("ongoing");
    document.getElementById("stat-completed").textContent = byStatus("completed");
    document.getElementById("stat-planned").textContent = byStatus("planned");
  }

  // ---------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------
  function populateBarangayDropdown(names) {
    const select = document.getElementById("gis-filter-barangay");
    names.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
  }

  function currentFilters() {
    const barangay = document.getElementById("gis-filter-barangay").value;
    const type = document.getElementById("gis-filter-type").value;
    const status = document.getElementById("gis-filter-status").value;
    const filters = {};
    if (barangay) filters.barangay = barangay;
    if (type) filters.type = type;
    if (status) filters.status = status;
    return filters;
  }

  function bindFilterEvents() {
    ["gis-filter-barangay", "gis-filter-type", "gis-filter-status"].forEach((id) => {
      document.getElementById(id).addEventListener("change", () => {
        const barangay = document.getElementById("gis-filter-barangay").value;
        loadProjects(currentFilters());
        if (barangay) highlightBarangay(barangay);
      });
    });
  }

  // ---------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------
  let searchDebounce = null;
  function bindSearch() {
    const input = document.getElementById("gis-search");
    input.addEventListener("input", () => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => runSearch(input.value.trim()), 300);
    });
  }

  function runSearch(q) {
    if (!q) return;

    // 1. Barangay name match -> zoom + highlight
    const matchedBarangay = allBarangayNames.find((n) => n.toLowerCase().includes(q.toLowerCase()));
    if (matchedBarangay) {
      highlightBarangay(matchedBarangay);
      return;
    }

    // 2. Project name/code match -> fit bounds to all its locations
    const filters = Object.assign({}, currentFilters(), { q });
    loadProjects(filters).then(() => {
      if (!projectFeaturesCache.length) return;
      const bounds = L.latLngBounds(
        projectFeaturesCache.map((f) => [f.geometry.coordinates[1], f.geometry.coordinates[0]])
      );
      map.fitBounds(bounds, { maxZoom: 16, padding: [40, 40] });
    });
  }

  // ---------------------------------------------------------------
  // Fullscreen + lightbox + misc UI
  // ---------------------------------------------------------------
  function bindFullscreen() {
    document.getElementById("gis-fullscreen-btn").addEventListener("click", () => {
      const shell = document.querySelector(".gis-map-shell");
      if (!document.fullscreenElement) {
        shell.requestFullscreen?.();
      } else {
        document.exitFullscreen?.();
      }
      setTimeout(() => map.invalidateSize(), 200);
    });
  }

  function openLightbox(src) {
    const lb = document.getElementById("gis-photo-lightbox");
    const img = document.getElementById("gis-lightbox-img");

    if (!lb || !img) return;

    img.src = src;
    lb.hidden = false;
    document.body.style.overflow = "hidden";
}

function closeLightbox() {
    const lb = document.getElementById("gis-photo-lightbox");
    const img = document.getElementById("gis-lightbox-img");

    if (!lb) return;

    lb.hidden = true;

    if (img) {
        img.src = "";
    }

    document.body.style.overflow = "";
}

function bindLightbox() {
    const lb = document.getElementById("gis-photo-lightbox");
    const closeButton = document.getElementById("gis-lightbox-close");

    if (!lb || !closeButton) return;

    // Close button
    closeButton.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        closeLightbox();
    });

    // Click outside the image to close
    lb.addEventListener("click", function (event) {
        if (event.target === lb) {
            closeLightbox();
        }
    });

    // ESC key to close
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !lb.hidden) {
            closeLightbox();
        }
    });
}

  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------
  (async function init() {
    bindFilterEvents();
    bindSearch();
    bindFullscreen();
    bindLightbox();

    await Promise.all([loadBarangays(), loadRoads(), loadBridges(), loadWaterways(), loadFacilities()]);
    await loadProjects({});
    focusConfiguredProject();

    window.addEventListener("resize", () => map.invalidateSize());
  })();
})();

