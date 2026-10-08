const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addCookies([{ name: 'sessionid', value: process.env.PICKER_SESSION, url: process.env.BASE_URL }]);
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({
      contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e3eedc" stroke="#657b5e"/></svg>',
    }));
    await page.route('https://fonts.**/**', route => route.abort());
    await page.addInitScript(() => {
      let leaflet;
      Object.defineProperty(window, 'L', { configurable: true, get: () => leaflet, set(value) {
        leaflet = value;
        const createMap = value.map, createMarker = value.marker;
        value.map = function (...args) { return window.testPickerMap = createMap.apply(this, args); };
        value.marker = function (...args) { return window.testPickerMarker = createMarker.apply(this, args); };
      } });
    });
    const values = () => page.evaluate(() => ({
      lat: document.getElementById('id_latitude').value,
      lng: document.getElementById('id_longitude').value,
    }));
    await page.goto(process.env.BASE_URL + process.env.PICKER_CREATE_PATH, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('#basic-information').isVisible(), true);
    assert.equal(await page.locator('#id_latitude').getAttribute('type'), 'hidden');
    assert.equal(await page.locator('#id_longitude').getAttribute('type'), 'hidden');
    await page.locator('#id_title').fill('Browser-selected infrastructure site');
    await page.locator('#id_description').fill('Map picker browser regression');
    await page.locator('#id_category').selectOption({ label: 'Roads Test' });
    await page.locator('#id_implementing_office').fill('Engineering Office');
    await page.locator('[data-wizard-next]').click();
    await page.waitForFunction(() => !!window.testPickerMap);
    const initial = await page.evaluate(() => ({ center: window.testPickerMap.getCenter(), zoom: window.testPickerMap.getZoom() }));
    assert.equal(initial.zoom, 12);
    assert(Math.abs(initial.center.lat - 15.4522) < 0.001 && Math.abs(initial.center.lng - 121.3387) < 0.001);
    assert.deepEqual(await values(), { lat: '', lng: '' });
    assert.equal(await page.locator('.leaflet-marker-icon').count(), 0);
    await page.locator('#id_street').fill('Main Street');
    await page.locator('#id_barangay').selectOption('Bagting');
    await page.locator('[data-wizard-next]').click();
    assert.equal(await page.locator('#project-location').isVisible(), true);
    assert.equal(await page.locator('[data-location-error]').isVisible(), true);
    console.log('PASS: create map centered on Gabaldon; empty coordinates block wizard progression');

    const map = page.locator('[data-location-map]');
    await map.click({ position: { x: 250, y: 200 } });
    const first = await values();
    assert.match(first.lat, /^-?\d+\.\d{7}$/);
    assert.match(first.lng, /^-?\d+\.\d{7}$/);
    assert.equal(await page.locator('[data-selected-latitude]').innerText(), first.lat);
    assert.equal(await page.locator('.leaflet-marker-icon').count(), 1);
    assert.equal(await page.locator('[data-location-error]').isVisible(), false);
    await map.click({ position: { x: 350, y: 220 } });
    assert.equal(await page.locator('.leaflet-marker-icon').count(), 1);
    const beforeDrag = await values();
    assert.notDeepEqual(beforeDrag, first);
    const markerBox = await page.locator('.leaflet-marker-icon').boundingBox();
    await page.mouse.move(markerBox.x + markerBox.width / 2, markerBox.y + markerBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(markerBox.x + markerBox.width / 2 + 60, markerBox.y + markerBox.height / 2 + 30, { steps: 10 });
    await page.mouse.up();
    await page.waitForFunction(before => document.getElementById('id_latitude').value !== before.lat, beforeDrag);
    assert.notDeepEqual(await values(), beforeDrag);
    await page.locator('[data-clear-location]').click();
    assert.deepEqual(await values(), { lat: '', lng: '' });
    assert.equal(await page.locator('.leaflet-marker-icon').count(), 0);
    await map.click({ position: { x: 400, y: 230 } });
    await page.locator('[data-wizard-next]').click();
    assert.equal(await page.locator('#funding-contract').isVisible(), true);
    await page.locator('[data-wizard-back]').click();
    await page.waitForFunction(() => window.testPickerMap.getSize().x === document.getElementById('infrastructure-location-map').clientWidth);
    assert.equal(await page.locator('.leaflet-marker-icon').count(), 1);
    console.log('PASS: click, replace, drag, clear, hidden coordinates and wizard reentry');

    await page.setViewportSize({ width: 390, height: 844 });
    await map.scrollIntoViewIfNeeded();
    await page.waitForFunction(() => window.testPickerMap.getSize().x === document.getElementById('infrastructure-location-map').clientWidth);
    assert.equal((await map.boundingBox()).height, 340);
    assert.equal(await page.locator('.leaflet-control-zoom-in').isVisible(), true);
    console.log('PASS: mobile picker resizing and controls');

    await page.goto(process.env.BASE_URL + process.env.PICKER_EDIT_PATH, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('#basic-information').isVisible(), true);
    await page.locator('[data-wizard-next]').click();
    await page.waitForFunction(() => !!window.testPickerMap);
    assert.deepEqual(await values(), { lat: '15.4541234', lng: '121.3375123' });
    assert.equal(await page.locator('.leaflet-marker-icon').count(), 1);
    assert.equal(await page.evaluate(() => window.testPickerMap.getZoom()), 16);
    const savedMarker = await page.evaluate(() => window.testPickerMarker.getLatLng());
    assert.equal(savedMarker.lat, 15.4541234);
    assert.equal(savedMarker.lng, 121.3375123);
    await map.click({ position: { x: 150, y: 200 } });
    assert.notDeepEqual(await values(), { lat: '15.4541234', lng: '121.3375123' });
    console.log('PASS: edit restores saved marker and replaces the selected point');

    await page.goto(process.env.BASE_URL + process.env.PICKER_MISSING_PATH, { waitUntil: 'networkidle' });
    await page.locator('[data-wizard-next]').click();
    await page.waitForFunction(() => !!window.testPickerMap);
    assert.deepEqual(await values(), { lat: '', lng: '' });
    assert.equal(await page.locator('.leaflet-marker-icon').count(), 0);
    assert.equal(await page.evaluate(() => window.testPickerMap.getZoom()), 12);
    assert.deepEqual(errors, []);
    console.log('PASS: legacy record without coordinates starts with no marker');
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
