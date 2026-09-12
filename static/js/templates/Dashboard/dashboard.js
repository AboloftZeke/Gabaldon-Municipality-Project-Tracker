(() => {
  const q = (selector, parent = document) => parent.querySelector(selector);
  const qa = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const unavailable = 'Not reported';

  const rows = qa('.project-row');
  const host = q('#project-card-grid');
  const table = q('.table-wrap');
  const count = q('#visible-count');
  const categorySelect = q('#category-filter');
  const locationSelect = q('#location-filter');
  const searchInput = q('#project-search');
  const tabs = qa('.tab-btn');
  const statuses = qa('.status-btn');
  const views = qa('[data-dashboard-view]');
  const mapHost = q('#project-gis-map');
  const mapCount = q('#gis-visible-count');
  const mapEmpty = q('#gis-empty-state');
  const mapStateTitle = q('#gis-state-title');
  const mapStateMessage = q('#gis-state-message');
  const mapRetryButton = q('#gis-retry-button');

  let category = 'all';
  let status = 'all';
  let projectMap = null;
  let mapTiles = null;
  let mapMarkers = null;
  let mapFeatures = [];
  let didFitMap = false;
  let mapUnavailable = false;
  let tileErrorCount = 0;

  const groups = categorySelect
    ? qa('optgroup', categorySelect).map((group) => ({
        type: group.dataset.projectCategoryType,
        label: group.label,
        items: qa('option', group).map((option) => [
          option.value,
          option.textContent,
        ]),
      }))
    : [];

  function formatCurrencyValues() {
    qa('[data-currency-value]').forEach((element) => {
      const amount = Number(element.dataset.currencyValue);
      if (!Number.isFinite(amount)) return;
      element.textContent = new Intl.NumberFormat('en-PH', {
        style: 'currency',
        currency: 'PHP',
        maximumFractionDigits: amount >= 1000000 ? 0 : 2,
      }).format(amount);
    });
  }

  function showMapState(title, message, canRetry = false) {
    if (mapEmpty) mapEmpty.hidden = false;
    if (mapStateTitle) mapStateTitle.textContent = title;
    if (mapStateMessage) mapStateMessage.textContent = message;
    if (mapRetryButton) mapRetryButton.hidden = !canRetry;
  }

  function hideMapState() {
    mapUnavailable = false;
    if (mapEmpty) mapEmpty.hidden = true;
    if (mapRetryButton) mapRetryButton.hidden = true;
  }

  function refreshCategories() {
    if (!categorySelect) return;
    const prior = categorySelect.value;
    const valid = new Set(['all']);
    categorySelect.replaceChildren();

    const all = document.createElement('option');
    all.value = 'all';
    all.textContent = category === 'infra'
      ? 'All Infrastructure Categories'
      : category === 'noninfra'
        ? 'All Non-Infrastructure Categories'
        : 'All Categories';
    categorySelect.append(all);

    groups.forEach((group) => {
      if (category !== 'all' && group.type !== category) return;
      const optionGroup = document.createElement('optgroup');
      optionGroup.label = group.label;
      group.items.forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        optionGroup.append(option);
        valid.add(value);
      });
      categorySelect.append(optionGroup);
    });
    categorySelect.value = valid.has(prior) ? prior : 'all';
  }

  function field(label, value) {
    const element = document.createElement('div');
    const key = document.createElement('span');
    const content = document.createElement('span');
    element.className = 'project-card__field';
    key.className = 'project-card__field-label';
    content.className = 'project-card__field-value';
    key.textContent = label;
    content.textContent = value || unavailable;
    element.append(key, content);
    return element;
  }

  const cards = host
    ? rows.map((row, index) => {
        const card = document.createElement('article');
        const thumb = q('.project-thumb', row);
        const image = document.createElement('img');
        const body = document.createElement('div');
        const title = document.createElement('h3');
        const location = q('.project-subtext', row)?.textContent.trim();
        const chip = q('.status-chip', row);
        const fields = document.createElement('div');
        const source = q('.row-link', row);

        card.className = 'project-card';
        card.dataset.projectIndex = index;
        image.className = 'project-card__image';
        image.src = thumb ? (thumb.currentSrc || thumb.src) : '';
        image.alt = thumb ? thumb.alt : 'Project cover';
        body.className = 'project-card__content';
        title.className = 'project-card__title';
        title.textContent = q('.project-title', row)?.textContent.trim()
          || 'Untitled project';
        body.append(title);

        if (location) {
          const locationText = document.createElement('p');
          locationText.className = 'project-card__location';
          locationText.textContent = location;
          body.append(locationText);
        }

        if (chip) body.append(chip.cloneNode(true));
        fields.className = 'project-card__fields';
        fields.append(
          field('Type', q('td:nth-child(2)', row)?.textContent.trim()),
          field('Budget / Cost', q('td:nth-child(4)', row)?.textContent.trim()),
          field('Progress', q('td:nth-child(5)', row)?.textContent.trim()),
        );
        body.append(fields);

        if (source) {
          const link = source.cloneNode(true);
          link.classList.add('project-card__action');
          link.addEventListener('click', (event) => {
            event.preventDefault();
            source.click();
          });
          body.append(link);
        }

        card.append(image, body);
        host.append(card);
        return card;
      })
    : [];

  function escapeHtml(value) {
    const node = document.createElement('span');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML;
  }

  function mapLocationKey(value) {
    const key = (value || '').trim().toLowerCase().replace(/\s+/g, '_');
    return key.startsWith('bitulok') ? 'bitulok' : key;
  }

  function mapStatusMatches(feature) {
    if (status === 'all') return true;
    const value = feature.properties.dashboard_status || '';
    return status === 'ongoing'
      ? ['ongoing', 'ongoing_bidding', 'awarded'].includes(value)
      : value === status;
  }

  function mapPopup(feature, imageUrl) {
    const project = feature.properties;
    const image = imageUrl
      ? '<img class="gis-popup__image" src="' + escapeHtml(imageUrl)
        + '" alt="' + escapeHtml(project.name) + ' cover">'
      : '';
    const budget = project.budget != null
      ? new Intl.NumberFormat('en-PH', {
          style: 'currency',
          currency: 'PHP',
          maximumFractionDigits: 2,
        }).format(Number(project.budget))
      : unavailable;
    const progress = project.progress != null
      ? Number(project.progress).toFixed(0) + '%'
      : unavailable;

    return '<article class="gis-popup">' + image
      + '<h3>' + escapeHtml(project.name) + '</h3>'
      + '<p class="gis-popup__meta">'
      + escapeHtml(project.category || project.type)
      + ' · ' + escapeHtml(project.barangay || 'Location not reported')
      + '</p><p><strong>Status:</strong> '
      + escapeHtml(project.status || unavailable)
      + '</p><p><strong>Budget / Cost:</strong> ' + budget
      + '</p><p><strong>Progress:</strong> ' + progress
      + '</p><a class="row-link gis-popup__action" href="'
      + escapeHtml(project.detail_url)
      + '">View Project Details</a></article>';
  }

  function mapMarker(feature) {
    const project = feature.properties;
    const colors = {
      planned: '#64748b',
      ongoing: '#d97706',
      awarded: '#2563eb',
      completed: '#15803d',
      cancelled: '#b91c1c',
      rebid: '#9333ea',
    };
    const color = colors[project.dashboard_status]
      || colors[project.status_key]
      || '#475569';

    const marker = L.circleMarker(
      [feature.geometry.coordinates[1], feature.geometry.coordinates[0]],
      {
        radius: 9,
        color: '#fff',
        weight: 2,
        fillColor: color,
        fillOpacity: 1,
      },
    );
    marker.bindPopup(mapPopup(feature, ''), { maxWidth: 260 });
    marker.on('popupopen', () => {
      fetch('/gis/projects/' + encodeURIComponent(project.project_id) + '/photos.json')
        .then((response) => (response.ok ? response.json() : null))
        .then((data) => {
          const cover = data?.photos?.find((photo) => photo.is_cover)
            || data?.photos?.[0];
          if (cover?.url) marker.setPopupContent(mapPopup(feature, cover.url));
        })
        .catch(() => {});
    });
    return marker;
  }

  function refreshMap() {
    if (!projectMap || !mapMarkers) return;

    const projectCategory = categorySelect?.value || 'all';
    const location = locationSelect?.value || 'all';
    const search = (searchInput?.value || '').trim().toLowerCase();
    const visible = mapFeatures.filter((feature) => {
      const project = feature.properties;
      const typeMatches = category === 'all'
        || (category === 'infra' && project.type === 'infrastructure')
        || (category === 'noninfra' && project.type === 'non_infrastructure');
      const categoryMatches = projectCategory === 'all'
        || project.category_key === projectCategory;
      const locationMatches = location === 'all'
        || mapLocationKey(project.barangay) === location;
      const searchText = [
        project.name,
        project.code,
        project.category,
        project.barangay,
        project.address,
        project.implementing_office,
        project.funding_source,
        project.status,
      ].join(' ').toLowerCase();

      return typeMatches && categoryMatches && locationMatches
        && mapStatusMatches(feature)
        && (!search || searchText.includes(search));
    });

    mapMarkers.clearLayers();
    visible.forEach((feature) => mapMarker(feature).addTo(mapMarkers));
    if (mapCount) {
      mapCount.textContent = 'Showing ' + visible.length + ' of '
        + mapFeatures.length + ' mapped projects';
    }

    if (!mapUnavailable) {
      if (visible.length) {
        hideMapState();
      } else {
        const hasUnmapped = rows.length > mapFeatures.length;
        showMapState(
          'No mapped projects found',
          hasUnmapped
            ? 'No matching projects have usable map coordinates yet.'
            : 'No mapped projects are available for the selected filters.',
        );
      }
    }

    if (visible.length && !didFitMap) {
      const coordinates = visible.map((feature) => [
        feature.geometry.coordinates[1],
        feature.geometry.coordinates[0],
      ]);
      if (coordinates.length === 1) {
        projectMap.setView(coordinates[0], 14);
      } else {
        projectMap.fitBounds(coordinates, { padding: [28, 28], maxZoom: 15 });
      }
      didFitMap = true;
    }
  }

  function loadMapData() {
    if (mapCount) mapCount.textContent = 'Loading mapped projects…';
    return fetch('/gis/layers/projects.json')
      .then((response) => {
        if (!response.ok) throw new Error('Map data unavailable');
        return response.json();
      })
      .then((data) => {
        mapFeatures = Array.isArray(data.features) ? data.features : [];
        mapUnavailable = false;
        refreshMap();
        requestAnimationFrame(() => projectMap?.invalidateSize({ pan: false }));
      })
      .catch(() => {
        mapUnavailable = true;
        if (mapCount) mapCount.textContent = 'Map temporarily unavailable';
        showMapState(
          'Map temporarily unavailable',
          'Project locations are unavailable at the moment. Please try again shortly.',
          true,
        );
      });
  }

  function retryMap() {
    tileErrorCount = 0;
    mapUnavailable = false;
    hideMapState();
    if (mapTiles) mapTiles.redraw();
    loadMapData();
  }

  function initMap() {
    if (!mapHost) return;
    if (!window.L) {
      mapUnavailable = true;
      if (mapCount) mapCount.textContent = 'Map temporarily unavailable';
      showMapState(
        'Map temporarily unavailable',
        'The map could not be loaded. Please try again shortly.',
        true,
      );
      return;
    }

    projectMap = L.map(mapHost, { scrollWheelZoom: false })
      .setView([15.45, 121.34], 12);
    mapTiles = L.tileLayer(
      'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      { maxZoom: 19, attribution: '© OpenStreetMap contributors' },
    ).addTo(projectMap);
    mapTiles.on('tileerror', () => {
      tileErrorCount += 1;
      if (tileErrorCount >= 3 && !mapUnavailable) {
        mapUnavailable = true;
        if (mapCount) mapCount.textContent = 'Map temporarily unavailable';
        showMapState(
          'Map temporarily unavailable',
          'The map background is unavailable at the moment. Please try again shortly.',
          true,
        );
      }
    });

    mapMarkers = L.layerGroup().addTo(projectMap);
    const resizeMap = () => projectMap.invalidateSize({ pan: false });
    requestAnimationFrame(resizeMap);
    window.addEventListener('resize', resizeMap);
    loadMapData();
  }

  function filter() {
    const projectCategory = categorySelect?.value || 'all';
    const location = locationSelect?.value || 'all';
    const search = (searchInput?.value || '').trim().toLowerCase();
    let shown = 0;

    rows.forEach((row, index) => {
      const show = (category === 'all' || row.dataset.category === category)
        && (projectCategory === 'all'
          || row.dataset.projectCategory === projectCategory)
        && (status === 'all' || row.dataset.status === status)
        && (location === 'all' || row.dataset.location === location)
        && (!search || row.textContent.toLowerCase().includes(search));

      row.classList.toggle('hidden-row', !show);
      if (cards[index]) cards[index].hidden = !show;
      if (show) shown += 1;
    });

    if (count) count.textContent = shown;
    refreshMap();
  }

  function setView(view) {
    const cardView = view === 'card';
    if (table) table.hidden = cardView;
    if (host) host.hidden = !cardView;
    views.forEach((button) => {
      const active = button.dataset.dashboardView === view;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active);
    });
    try {
      sessionStorage.setItem('dashboard-view', cardView ? 'card' : 'detail');
    } catch (_) {}
  }

  tabs.forEach((button) => button.addEventListener('click', () => {
    category = button.dataset.category || 'all';
    tabs.forEach((item) => item.classList.remove('is-active'));
    button.classList.add('is-active');
    refreshCategories();
    filter();
  }));

  categorySelect?.addEventListener('change', filter);
  locationSelect?.addEventListener('change', filter);
  searchInput?.addEventListener('input', filter);
  statuses.forEach((button) => button.addEventListener('click', () => {
    status = button.dataset.status || 'all';
    statuses.forEach((item) => item.classList.remove('is-active'));
    button.classList.add('is-active');
    filter();
  }));
  views.forEach((button) => button.addEventListener(
    'click',
    () => setView(button.dataset.dashboardView),
  ));
  mapRetryButton?.addEventListener('click', retryMap);

  formatCurrencyValues();
  refreshCategories();
  initMap();
  filter();
  try {
    setView(sessionStorage.getItem('dashboard-view') === 'card' ? 'card' : 'detail');
  } catch (_) {
    setView('detail');
  }
})();
