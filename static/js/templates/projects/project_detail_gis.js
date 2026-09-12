(function () {
    const mapElement = document.querySelector('[data-project-map]');
    const lightbox = document.querySelector('[data-lightbox]');

    if (!mapElement || typeof L === 'undefined') {
        return;
    }

    const shell = document.querySelector('[data-project-gis-shell]');
    const messagePanel = document.querySelector('[data-project-map-message]');
    const fullscreenButton = document.querySelector('[data-map-fullscreen]');
    const hasCoordinates = mapElement.dataset.hasCoordinates === 'true';
    const projectName = mapElement.dataset.projectName || 'Project Location';
    const projectCode = mapElement.dataset.projectCode || '';
    const projectType = mapElement.dataset.projectType || '';
    const projectBarangay = mapElement.dataset.projectBarangay || '';
    const projectStatus = mapElement.dataset.projectStatus || '';
    const projectBudget = mapElement.dataset.projectBudget || '';
    const projectProgress = mapElement.dataset.projectProgress || '';
    const projectGoogleMapsUrl = mapElement.dataset.googleMapsUrl || '#';
    const detailUrl = mapElement.dataset.detailUrl || '#';
    const fallbackLat = parseFloat(mapElement.dataset.mapCenterLat || '15.2915');
    const fallbackLng = parseFloat(mapElement.dataset.mapCenterLng || '121.3386');
    const zoomLevel = Number(mapElement.dataset.mapZoom || 16);
    const startLat = Number.isFinite(parseFloat(mapElement.dataset.mapCenterLat)) ? parseFloat(mapElement.dataset.mapCenterLat) : fallbackLat;
    const startLng = Number.isFinite(parseFloat(mapElement.dataset.mapCenterLng)) ? parseFloat(mapElement.dataset.mapCenterLng) : fallbackLng;

    const streetLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
    });

    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri',
    });

    const terrainLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
        maxZoom: 17,
        attribution: '&copy; OpenStreetMap contributors, SRTM | Map style: &copy; OpenTopoMap',
    });

    const offlineLayer = L.gridLayer({ tileSize: 256 });
    offlineLayer.createTile = function () {
        const tile = document.createElement('canvas');
        tile.width = 256;
        tile.height = 256;
        const context = tile.getContext('2d');
        if (!context) {
            return tile;
        }

        context.fillStyle = '#edf4ef';
        context.fillRect(0, 0, 256, 256);
        context.strokeStyle = '#cbd5cf';
        for (let i = 0; i <= 256; i += 32) {
            context.beginPath();
            context.moveTo(i, 0);
            context.lineTo(i, 256);
            context.stroke();
            context.beginPath();
            context.moveTo(0, i);
            context.lineTo(256, i);
            context.stroke();
        }
        context.fillStyle = '#2E6F40';
        context.font = 'bold 12px sans-serif';
        context.fillText('Offline basemap', 12, 20);
        return tile;
    };

    const map = L.map(mapElement, {
        zoomControl: true,
        layers: [streetLayer],
    }).setView([startLat, startLng], hasCoordinates ? zoomLevel : 14);

    let activeLayer = streetLayer;
    let offlineFallbackActivated = false;
    let projectMarker = null;

    function activateOfflineFallback() {
        if (offlineFallbackActivated) {
            return;
        }
        offlineFallbackActivated = true;
        if (activeLayer) {
            map.removeLayer(activeLayer);
        }
        activeLayer = offlineLayer.addTo(map);
        if (messagePanel && !hasCoordinates) {
            messagePanel.hidden = false;
        }
    }

    streetLayer.on('tileerror', activateOfflineFallback);
    satelliteLayer.on('tileerror', activateOfflineFallback);
    terrainLayer.on('tileerror', activateOfflineFallback);

    const baseLayers = {
        'Street Map': streetLayer,
        'Satellite': satelliteLayer,
        'Terrain': terrainLayer,
    };

    L.control.layers(baseLayers, null, { collapsed: false }).addTo(map);
    L.control.scale({ imperial: false }).addTo(map);

    function buildPopup() {
        return `
            <div class="project-map-popup">
                <div class="popup-badge">${projectType}</div>
                <h4>${projectName}</h4>
                <p><strong>Project Code:</strong> ${projectCode}</p>
                <p><strong>Barangay:</strong> ${projectBarangay}</p>
                <p><strong>Status:</strong> ${projectStatus}</p>
                <p><strong>Budget:</strong> ${projectBudget}</p>
                <p><strong>Progress:</strong> ${projectProgress}</p>
                <a href="${detailUrl}">View Full Details</a>
            </div>
        `;
    }

    function createMarkerIcon() {
        return L.divIcon({
            className: '',
            html: `<div class="project-map-marker ${projectType === 'Infrastructure' ? 'project-map-marker--infra' : 'project-map-marker--noninfra'}"><span>${projectType === 'Infrastructure' ? '🏗' : '📋'}</span></div>`,
            iconSize: [36, 36],
            iconAnchor: [18, 36],
            popupAnchor: [0, -28],
        });
    }

    if (hasCoordinates) {
        projectMarker = L.marker([parseFloat(mapElement.dataset.mapCenterLat), parseFloat(mapElement.dataset.mapCenterLng)], {
            icon: createMarkerIcon(),
        }).addTo(map);
        projectMarker.bindPopup(buildPopup());
    } else {
    map.setView([fallbackLat, fallbackLng], 14);

    if (messagePanel) {
        messagePanel.textContent =
            mapElement.dataset.projectGisMessage ||
            'Location has not yet been assigned.';
        messagePanel.hidden = false;
    }
}

    if (fullscreenButton) {
        fullscreenButton.addEventListener('click', () => {
            const container = shell || mapElement;
            if (!document.fullscreenElement) {
                container.requestFullscreen?.();
            } else {
                document.exitFullscreen?.();
            }
            window.setTimeout(() => map.invalidateSize(), 250);
        });
    }

    const lightboxImage = lightbox ? lightbox.querySelector('[data-lightbox-image]') : null;
    const lightboxCaption = lightbox ? lightbox.querySelector('[data-lightbox-caption]') : null;
    const lightboxCloseButtons = lightbox ? Array.from(lightbox.querySelectorAll('[data-lightbox-close]')) : [];

    function openLightbox(src) {
        const lb = document.getElementById("gis-photo-lightbox");
        const img = document.getElementById("gis-lightbox-img");

        if (!lb || !img) return;

        img.src = src;
        lb.hidden = false;
        lb.setAttribute("aria-hidden", "false");

        document.body.style.overflow = "hidden";
    }

    function closeLightbox() {
        const lb = document.getElementById("gis-photo-lightbox");
        const img = document.getElementById("gis-lightbox-img");

        if (!lb) return;

        lb.hidden = true;
        lb.setAttribute("aria-hidden", "true");

        if (img) {
            img.src = "";
        }

        document.body.style.overflow = "";
    }

        
    
    lightboxCloseButtons.forEach((button) => button.addEventListener('click', closeLightbox));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && lightbox && !lightbox.hidden) {
            closeLightbox();
        }
    });

    document.addEventListener('click', (event) => {
        const imageButton = event.target.closest('[data-image-src]');
        if (imageButton) {
            const src = imageButton.dataset.imageSrc;
            const caption = imageButton.dataset.imageCaption || '';
            openLightbox(src, caption);
        }
    });

    
})();