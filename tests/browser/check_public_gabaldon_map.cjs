// Run through run_public_gabaldon_map.py against isolated published fixtures.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [], projectRequests = [];
    let offline = false;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (/\/gis\/(layers\/projects\.json|projects\/)/.test(request.url())) projectRequests.push(request.url());
    });
    // Deterministic image tiles exercise real Leaflet CSS/layout without relying
    // on a third-party tile service. These labeled squares are test fixtures.
    await page.route('https://tile.openstreetmap.org/**', route => offline
      ? route.abort()
      : route.fulfill({ contentType: 'image/svg+xml', body:
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e3eedc" stroke="#657b5e"/><text x="20" y="128">Test tile</text></svg>' }));
    await page.route('https://fonts.**/**', route => route.abort());
    await page.addInitScript(() => {
      let leaflet;
      Object.defineProperty(window, 'L', {
        configurable: true,
        get: () => leaflet,
        set(value) {
          leaflet = value;
          const create = value.map;
          value.map = function (...args) {
            const map = create.apply(this, args);
            window.testPublicMap = map;
            return map;
          };
        },
      });
    });
    const url = `${process.env.BASE_URL}/dashboard/`;
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.locator('#gabaldon-public-map').scrollIntoViewIfNeeded();
    const mapState = () => page.evaluate(() => ({
      center: window.testPublicMap.getCenter(), zoom: window.testPublicMap.getZoom(),
    }));
    let state = await mapState();
    assert(Math.abs(state.center.lat - 15.4522) < 0.001);
    assert(Math.abs(state.center.lng - 121.3387) < 0.001);
    assert.equal(state.zoom, 12);
    assert.equal(await page.locator('.leaflet-marker-icon, .leaflet-interactive').count(), 0);
    assert(await page.locator('.leaflet-control-attribution').innerText().then(s => s.includes('OpenStreetMap')));
    assert.equal(await page.locator('#municipal-map-status').isVisible(), false);
    assert.equal(await page.locator('text=GIS Project Map').count(), 0);
    const tiles = await page.locator('.leaflet-tile').evaluateAll(nodes => nodes.map(node => {
      const rect = node.getBoundingClientRect(), style = getComputedStyle(node);
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
        naturalWidth: node.naturalWidth, position: style.position };
    }));
    assert(tiles.length >= 4);
    assert(tiles.every(tile => tile.naturalWidth === 256 && tile.width === 256 && tile.height === 256 && tile.position === 'absolute'));
    const xs = [...new Set(tiles.map(tile => tile.x))].sort((a, b) => a - b);
    const ys = [...new Set(tiles.map(tile => tile.y))].sort((a, b) => a - b);
    for (const positions of [xs, ys]) {
      for (let i = 1; i < positions.length; i++) assert.equal(positions[i] - positions[i - 1], 256);
    }
    console.log('PASS: local Leaflet assets, Gabaldon center, continuous tile layout, controls and attribution');

    await page.locator('.leaflet-control-zoom-in').click();
    await page.waitForFunction(() => window.testPublicMap.getZoom() === 13 && !window.testPublicMap._animatingZoom);
    const centerBeforePan = (await mapState()).center;
    const box = await page.locator('#gabaldon-public-map').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 100, box.y + box.height / 2 + 50, { steps: 10 });
    await page.mouse.up();
    await page.waitForFunction(before => {
      const center = window.testPublicMap.getCenter();
      return center.lat !== before.lat || center.lng !== before.lng;
    }, centerBeforePan);
    assert.notDeepEqual((await mapState()).center, centerBeforePan);
    console.log('PASS: zoom and free panning');

    for (const [type, total] of [['infra', 1], ['noninfra', 3]]) {
      await page.goto(`${url}?type=${type}`, { waitUntil: 'networkidle' });
      assert.equal(await page.locator('#visible-count').innerText(), String(total));
      const initialState = await mapState();
      await page.locator('#project-search').fill('no matching project');
      assert.equal(await page.locator('#visible-count').innerText(), '0');
      await page.locator('#project-search').fill(type === 'infra' ? 'Normalized Road' : 'Ongoing Program');
      assert.equal(await page.locator('#visible-count').innerText(), '1');
      await page.locator('#project-search').fill('');
      await page.locator('.status-btn[data-status="completed"]').click();
      assert.equal(await page.locator('#visible-count').innerText(), type === 'infra' ? '0' : '1');
      await page.locator('.status-btn[data-status="all"]').click();
      if (type === 'infra') {
        const row = await page.locator('.project-row').evaluate(node => node.dataset);
        await page.locator('#category-filter').selectOption(row.projectCategory);
        await page.locator('#location-filter').selectOption(row.location);
        assert.equal(await page.locator('#visible-count').innerText(), '1');
        await page.locator('#category-filter').selectOption('all');
        await page.locator('#location-filter').selectOption('all');
      }
      await page.locator('[data-dashboard-view="card"]').click();
      assert.equal(await page.locator('#project-card-grid').isVisible(), true);
      assert.deepEqual(await mapState(), initialState);
    }
    assert.deepEqual(projectRequests, []);
    console.log('PASS: both registries, search/status/category/location filters, card view, no project-map requests or synchronization');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#gabaldon-public-map').scrollIntoViewIfNeeded();
    await page.waitForFunction(() => {
      const element = document.getElementById('gabaldon-public-map');
      return window.testPublicMap.getSize().x === element.clientWidth;
    });
    const mobile = await page.locator('#gabaldon-public-map').boundingBox();
    assert.equal(mobile.height, 360);
    assert(mobile.width < 390 && mobile.width > 200);
    assert.equal(await page.locator('.leaflet-control-zoom-in').isVisible(), true);
    console.log('PASS: mobile height, controls and map resize');

    offline = true;
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await page.locator('#municipal-map-status').isVisible(), true);
    offline = false;
    await page.locator('#gabaldon-public-map').scrollIntoViewIfNeeded();
    await page.locator('.leaflet-control-zoom-in').click();
    await page.waitForFunction(() => document.getElementById('municipal-map-status').hidden);
    console.log('PASS: tile outage notice and recovery');
    assert.deepEqual(errors, []);
    await context.close();
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
