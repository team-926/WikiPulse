import { chromium } from '../../frontend/node_modules/@playwright/test/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';

const output = new URL('./', import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
const auditPrefix = process.env.PULSE_AUDIT_NAME || '';
const variants = [
  ['baseline', ''],
  ['scan-paused', ''],
  ['title-blur-off', '.document-cluster__title-glow { filter: none !important; }'],
  ['document-labels-hidden', '.document-node-label { display: none !important; }'],
  ['all-filters-off', '.document-map * { filter: none !important; }'],
];
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const summarize = metrics => Object.fromEntries(metrics.metrics.map(m => [m.name, m.value]));

async function run(name, css, throttle, repeat, profile = false) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  await page.goto(`${process.env.PULSE_AUDIT_URL || 'http://127.0.0.1:5188'}/#/pulse`);
  const map = page.locator('.document-map');
  await map.locator('.document-node').first().waitFor();
  await page.evaluate(() => document.fonts.ready);
  await map.locator('.document-map__controls button').last().click();
  if (name === 'scan-paused') await map.locator('.document-map__controls button').first().click();
  if (name === 'offscreen-hidden') {
    await map.evaluate(el => {
      const view = el.querySelector(':scope > svg').getBoundingClientRect();
      for (const c of el.querySelectorAll('.document-cluster')) {
        const b = c.getBoundingClientRect();
        if (b.right < view.left || b.left > view.right || b.bottom < view.top || b.top > view.bottom) c.dataset.auditOffscreen = 'true';
      }
    });
  }
  if (name === 'label-size-frozen') {
    await map.locator('.document-node-label__text').evaluateAll(es => {
      const sizes = es.map(e => getComputedStyle(e).fontSize);
      es.forEach((e, i) => e.style.setProperty('--audit-font', sizes[i]));
    });
  }
  if (css) await page.addStyleTag({ content: css });
  const counts = await map.evaluate(el => {
    const svg = el.querySelector(':scope > svg'), view = svg.getBoundingClientRect();
    const clusters = [...el.querySelectorAll('.document-cluster')];
    return {
      clusters: clusters.length,
      nodes: el.querySelectorAll('.document-node').length,
      edges: el.querySelectorAll('.document-edges line').length,
      elements: el.querySelectorAll('*').length,
      scanTargets: el.querySelectorAll('[data-scan-x]').length,
      visibleClusters: clusters.filter(c => {
        const b = c.querySelector('.document-cluster__boundary').getBoundingClientRect();
        return b.right > view.left && b.left < view.right && b.bottom > view.top && b.top < view.bottom;
      }).length,
    };
  });
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: throttle });
  const bounds = await map.locator(':scope > svg').boundingBox();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await wait(400);
  if (profile) {
    await cdp.send('Profiler.enable');
    await cdp.send('Profiler.setSamplingInterval', { interval: 1000 });
    await cdp.send('Profiler.start');
  }
  await page.evaluate(instrument => {
    window.audit = { frames: [], start: performance.now(), mutations: {}, zoomCommits: 0 };
    const tick = now => { window.audit.frames.push(now); window.audit.frame = requestAnimationFrame(tick); };
    window.audit.frame = requestAnimationFrame(tick);
    if (instrument) {
      window.audit.observer = new MutationObserver(records => {
        for (const r of records) {
          const key = `${r.target.getAttribute('class') || r.target.tagName}:${r.attributeName}`;
          window.audit.mutations[key] = (window.audit.mutations[key] || 0) + 1;
          if (r.attributeName === 'data-zoom') window.audit.zoomCommits++;
        }
      });
      window.audit.observer.observe(document.querySelector('.document-map'), { attributes: true, subtree: true });
    }
  }, profile);
  const before = summarize(await cdp.send('Performance.getMetrics'));
  for (let i = 0; i < 24; i++) {
    await page.mouse.wheel(0, Math.floor(i / 3) % 2 ? 80 : -80);
    await wait(85);
  }
  await wait(650);
  const after = summarize(await cdp.send('Performance.getMetrics'));
  const frames = await page.evaluate(() => {
    const a = window.audit;
    cancelAnimationFrame(a.frame); a.observer?.disconnect();
    const gaps = a.frames.slice(1).map((t, i) => t - a.frames[i]).sort((a, b) => a - b);
    return {
      durationMs: performance.now() - a.start,
      rafFps: (a.frames.length - 1) * 1000 / (a.frames.at(-1) - a.frames[0]),
      frameP50: gaps[Math.floor(gaps.length * .5)], frameP95: gaps[Math.floor(gaps.length * .95)],
      framesOver25: gaps.filter(v => v > 25).length, framesOver50: gaps.filter(v => v > 50).length,
      frameCount: gaps.length, zoomCommits: a.zoomCommits, mutations: a.mutations,
    };
  });
  const timings = Object.fromEntries(['ScriptDuration', 'LayoutDuration', 'RecalcStyleDuration', 'TaskDuration', 'LayoutCount', 'RecalcStyleCount'].map(k => [k, after[k] - before[k]]));
  if (profile) {
    const { profile: cpu } = await cdp.send('Profiler.stop');
    await writeFile(new URL(`${auditPrefix}baseline.cpuprofile`, output), JSON.stringify(cpu));
    const nodes = new Map(cpu.nodes.map(n => [n.id, n]));
    const samples = new Map();
    cpu.samples?.forEach((id, i) => samples.set(id, (samples.get(id) || 0) + (cpu.timeDeltas?.[i] || 1000)));
    const top = [...samples].sort((a, b) => b[1] - a[1]).slice(0, 35).map(([id, us]) => ({ ms: us / 1000, ...nodes.get(id).callFrame }));
    await writeFile(new URL(`${auditPrefix}profile-summary.json`, output), JSON.stringify({ top, mutations: frames.mutations, zoomCommits: frames.zoomCommits }, null, 2));
  }
  const result = { name, throttle, repeat, profile, counts, ...frames, ...timings };
  delete result.mutations;
  results.push(result);
  console.log(JSON.stringify(result));
  await page.close();
}

try {
  if (process.argv.includes('--label-variants')) {
    for (let repeat = 0; repeat < 2; repeat++) {
      await run('contained-labels', '.document-node-label__box { contain:layout style paint; }', 1, repeat);
      await run('label-transforms-off', '.document-node-label__text { transform:none !important; }', 1, repeat);
    }
  } else if (process.argv.includes('--baseline-only')) {
    for (let repeat = 0; repeat < 2; repeat++) await run('baseline', '', 1, repeat);
    for (let repeat = 0; repeat < 2; repeat++) await run('baseline', '', 4, repeat);
    await run('baseline-profile', '', 1, 0, true);
  } else if (process.argv.includes('--focused')) {
    for (let repeat = 0; repeat < 2; repeat++) {
      for (const [name, css] of [
        ['baseline', ''],
        ['offscreen-hidden', '[data-audit-offscreen] { display:none !important; }'],
        ['label-size-frozen', '.document-node-label__text { font-size:var(--audit-font) !important; }'],
        ['scan-paused', ''],
      ]) await run(name, css, 1, repeat);
    }
  } else {
  for (let repeat = 0; repeat < 2; repeat++) await run('baseline', '', 1, repeat);
  for (let repeat = 0; repeat < 2; repeat++) {
    for (const [name, css] of repeat ? [...variants].reverse() : variants) await run(name, css, 4, repeat);
  }
  await run('baseline-profile', '', 1, 0, true);
  }
} finally {
  await writeFile(new URL(auditPrefix + (process.argv.includes('--focused') ? 'zoom-focused-results.json' : 'zoom-results.json'), output), JSON.stringify(results, null, 2));
  await browser.close();
}
