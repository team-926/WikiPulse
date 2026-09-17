import { chromium, expect } from '../../frontend/node_modules/@playwright/test/index.mjs';

const browser = await chromium.launch();
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 }, reducedMotion: 'reduce' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:5189/#/pulse');
    const map = page.locator('.document-map');
    await expect(map.locator('.document-node').first()).toBeAttached();
    await page.evaluate(() => document.fonts.ready);
    await map.scrollIntoViewIfNeeded();
    await map.locator('.document-map__controls button').nth(4).click();
    const svg = map.locator('svg[role=group]');
    await page.screenshot({ path: `.impeccable/performance/optimized-${width}-default.png` });
    await map.locator('.document-map__controls button').nth(width === 390 ? 2 : 1).click();
    await map.locator('.document-map__controls button').nth(width === 390 ? 2 : 1).click();
    await page.screenshot({ path: `.impeccable/performance/optimized-${width}-zoom.png` });
    const cluster = map.locator('.document-cluster[data-rank="0"]');
    if (width > 720) {
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      const center = await cluster.evaluate(element => {
        const point = new DOMPoint(0, 0).matrixTransform(element.getScreenCTM());
        return { x: point.x, y: point.y };
      });
      await page.mouse.move(center.x + 55, center.y + 30);
      await expect(cluster.locator('.document-cluster__orbit')).toHaveCSS('opacity', '0.8');
      const angle1 = await cluster.evaluate(element => element.style.getPropertyValue('--orbit-angle'));
      await page.mouse.move(center.x - 50, center.y + 40);
      const angle2 = await cluster.evaluate(element => element.style.getPropertyValue('--orbit-angle'));
      expect(angle1).not.toBe(angle2);
      await expect.poll(() => cluster.locator('.document-cluster__heading').evaluate(element => Number(element.style.getPropertyValue('--scan-strength'))), { timeout: 6000, intervals: [20] }).toBeGreaterThan(0.6);
      await page.screenshot({ path: `.impeccable/performance/optimized-${width}-glow.png` });
      const box = await svg.boundingBox();
      await page.mouse.move(box.x + 12, box.y + box.height - 15);
      await page.mouse.down();
      await page.mouse.move(box.x + 45, box.y + box.height - 40, { steps: 4 });
      await page.mouse.up();
      await expect(svg).toHaveCSS('outline-style', 'none');
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    expect(errors).toEqual([]);
    console.log(JSON.stringify({ width, errors, nodes: await map.locator('.document-node').count(), renderedClusters: await svg.getAttribute('data-rendered-clusters') }));
    await page.close();
  }
} finally {
  await browser.close();
}
