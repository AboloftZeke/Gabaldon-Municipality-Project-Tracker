(function () {
  "use strict";

  const container = document.getElementById("gabaldon-public-map");
  if (!container) return;

  const status = document.getElementById("municipal-map-status");
  function showStatus(message) {
    if (!status) return;
    status.textContent = message;
    status.hidden = !message;
  }

  if (!window.L) {
    showStatus("The interactive map could not be loaded. Please reload the page.");
    return;
  }

  const map = L.map(container).setView([15.4522, 121.3387], 12);
  const basemap = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  });

  let loadedTiles = 0;
  basemap.on("loading", () => { loadedTiles = 0; });
  basemap.on("tileload", () => { loadedTiles += 1; });
  basemap.on("load", () => {
    showStatus(loadedTiles ? "" : "Map tiles are currently unavailable. Check your connection and try panning or zooming again.");
  });
  basemap.addTo(map);
  L.control.scale({ imperial: false }).addTo(map);

  let pendingResize;
  function resizeMap() {
    cancelAnimationFrame(pendingResize);
    pendingResize = requestAnimationFrame(() => map.invalidateSize({ pan: false }));
  }
  if (window.ResizeObserver) new ResizeObserver(resizeMap).observe(container);
  window.addEventListener("resize", resizeMap);
  resizeMap();
})();
