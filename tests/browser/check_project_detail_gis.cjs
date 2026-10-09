const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
  });
  try {
    const page = await browser.newPage(), errors = [], cdnRequests = [];
    let offline = false;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.url().includes('unpkg.com')) cdnRequests.push(request.url()); });
    await page.route('https://fonts.**/**', route => route.abort());
    await page.route('https://tile.openstreetmap.org/**', route => offline ? route.abort() : route.fulfill({
      contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e3eedc"/></svg>',
    }));
    await page.route('**/gis/layers/barangays.json', route => route.fulfill({ json: { type: 'FeatureCollection', features: [] } }));
    await page.route('**/media/**', route => route.fulfill({
      contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="192"><rect width="256" height="192" fill="#e3eedc"/></svg>',
    }));
    await page.route('**/gis/layers/projects.json', async route => {
      const response = await route.fetch(), data = await response.json();
      for (const feature of data.features) {
        feature.properties.address = 'LongAddressWithoutSpaces'.repeat(15);
        feature.properties.funding_source = 'LongFundingSourceWithoutSpaces'.repeat(15);
      }
      await route.fulfill({ json: data });
    });
    await page.addInitScript(() => {
      let leaflet;
      Object.defineProperty(window, 'L', { configurable: true, get: () => leaflet, set(value) {
        leaflet = value;
        const original = value.map;
        value.map = function (...args) { return window.testDetailMap = original.apply(this, args); };
      } });
    });
    await page.goto(process.env.BASE_URL + '/dashboard/', { waitUntil: 'networkidle' });
    const detailPath = await page.locator('[data-project-detail-url]').first().getAttribute('data-project-detail-url');
    for (const width of [1440, 768, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(process.env.BASE_URL + detailPath, { waitUntil: 'networkidle' });
      await page.waitForSelector('.gis-popup-project');
      const layout = await page.locator('.gis-popup-project').evaluate(popup => {
        const table = popup.querySelector('table'), content = popup.closest('.leaflet-popup-content');
        return { tableWidth: table.getBoundingClientRect().width, contentWidth: content.clientWidth,
          tableScroll: table.scrollWidth, tableClient: table.clientWidth, minWidth: getComputedStyle(table).minWidth };
      });
      assert.equal(layout.minWidth, '0px');
      assert(layout.tableWidth <= layout.contentWidth + 1, JSON.stringify(layout));
      assert(layout.tableScroll <= layout.tableClient + 1, JSON.stringify(layout));
      assert.equal(await page.locator('#gis-tile-fallback-banner').isVisible(), false);
      assert.equal(await page.evaluate(() => typeof L.markerClusterGroup), 'function');
      const tiles = await page.locator('.leaflet-tile').evaluateAll(nodes => nodes.map(n => ({ width: n.naturalWidth, position: getComputedStyle(n).position })));
      assert(tiles.length > 0 && tiles.every(t => t.width === 256 && t.position === 'absolute'));
      await page.locator('#gabaldon-gis-map').scrollIntoViewIfNeeded();
      await page.locator('.leaflet-control-zoom-in').click();
      await page.waitForFunction(() => !window.testDetailMap._animatingZoom);
      console.log(`PASS ${width}px: popup table stays contained, long values wrap, local Leaflet/clustering, tiles and controls`);
    }
    offline = true;
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await page.locator('#gis-tile-fallback-banner').isVisible(), true);
    assert.equal(await page.locator('.gis-popup-project').count(), 1);
    offline = false;
    await page.locator('#gis-retry-tiles').click();
    await page.waitForFunction(() => document.getElementById('gis-tile-fallback-banner').hidden);
    assert.equal(await page.locator('#gabaldon-gis-map').evaluate(e => e.classList.contains('gis-no-basemap')), false);
    assert.deepEqual(cdnRequests, []);
    assert.deepEqual(errors, []);
    console.log('PASS: visible tile outage notice, preserved project popup, retry recovery and no CDN dependencies');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
