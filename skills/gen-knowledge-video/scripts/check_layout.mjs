#!/usr/bin/env node
/**
 * Find text that overflows the 1920x1080 stage or collides with the subtitle.
 *
 * Usage (from the lesson directory):
 *   node check_layout.mjs [--warn] [--step 0.5]
 *
 * It walks the timeline, calls renderAt(t) at a fixed step, and inspects every
 * visible element that directly contains text. This catches the failure mode
 * that screenshots of short placeholder copy miss: a longer real sentence
 * wrapping out of its card, a big heading running off the right edge, or body
 * text sliding under the 44px subtitle.
 *
 * Exit 1 when issues are found (use --warn to report without failing).
 * Environment: SCENE, BROWSER_PATH, WIDTH, HEIGHT (same as render_range.mjs).
 */

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const warnOnly = args.includes('--warn');
const stepArg = args.indexOf('--step');
const step = stepArg >= 0 ? Number(args[stepArg + 1]) : 0.5;
if (!Number.isFinite(step) || step <= 0) {
  console.error('usage: node check_layout.mjs [--warn] [--step 0.5]');
  process.exit(2);
}

const width = Number(process.env.WIDTH) || 1920;
const height = Number(process.env.HEIGHT) || 1080;
const requireFromCwd = createRequire(path.join(process.cwd(), 'package.json'));

let chromium;
try {
  ({ chromium } = requireFromCwd('playwright'));
} catch {
  try {
    ({ chromium } = requireFromCwd('playwright-core'));
  } catch {
    console.error(
      'playwright not found. From the lesson directory run:\n' +
        '  npm i playwright && npx playwright install chromium\n' +
        'or install playwright-core and set BROWSER_PATH to Chrome/Edge.'
    );
    process.exit(2);
  }
}

const candidates = [
  process.env.BROWSER_PATH,
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/snap/bin/chromium',
  '/usr/bin/microsoft-edge',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  process.env.LOCALAPPDATA &&
    path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe'),
  process.env.LOCALAPPDATA &&
    path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
].filter(Boolean);
const executablePath = candidates.find((p) => fs.existsSync(p));

const launchOptions = {
  headless: true,
  args: ['--force-device-scale-factor=1', '--hide-scrollbars', '--disable-lcd-text'],
};
if (executablePath) launchOptions.executablePath = executablePath;

const scenePath = path.resolve(process.env.SCENE || 'scene.html');
if (!fs.existsSync(scenePath)) {
  console.error(`scene not found: ${scenePath}`);
  process.exit(2);
}

const browser = await chromium.launch(launchOptions);
const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
const timingProblems = [];

page.on('console', (msg) => {
  if (/missing cue|no cues for segment/i.test(msg.text())) timingProblems.push(msg.text());
});
page.on('pageerror', (err) => timingProblems.push(`pageerror: ${err.message}`));

await page.goto(pathToFileURL(scenePath).href);
await page.evaluate(() => document.fonts.ready);
await page.waitForFunction(() => typeof window.renderAt === 'function');
await page.waitForTimeout(300);

const total = await page.evaluate(() => window.TIMELINE?.total || 0);
if (!total) {
  console.error('window.TIMELINE is missing or has no total; build audio first');
  await browser.close();
  process.exit(1);
}

const issues = new Map();
for (let t = 0.6; t <= total; t += step) {
  await page.evaluate((time) => window.renderAt(time), t);
  const found = await page.evaluate(() => {
    const out = [];
    const items = [];
    const stage = document.getElementById('stage');
    if (!stage) return out;
    const stageRect = stage.getBoundingClientRect();
    const sub = document.getElementById('subtitle');
    const subVisible =
      sub && Number(getComputedStyle(sub).opacity) > 0.9 && sub.textContent.trim();
    const subRect = subVisible ? sub.getBoundingClientRect() : null;

    const isVisible = (el) => {
      for (let n = el; n; n = n.parentElement) {
        const cs = getComputedStyle(n);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        if (Number(cs.opacity) < 0.95) return false;
      }
      return true;
    };
    const nameOf = (el) => {
      if (el.id) return '#' + el.id;
      if (typeof el.className === 'string' && el.className.trim()) {
        return '.' + el.className.trim().split(/\s+/).join('.');
      }
      return el.tagName.toLowerCase();
    };

    for (const el of stage.querySelectorAll('*')) {
      if (el === stage) continue;
      if (el.closest('#grid') || el.closest('#progress-wrap')) continue;
      const directText = [...el.childNodes].some(
        (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim()
      );
      if (!directText && el.id !== 'subtitle') continue;
      if (!isVisible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      const name = nameOf(el);
      const cs = getComputedStyle(el);
      items.push({ el, name, r });

      if (
        r.left < stageRect.left - 1 ||
        r.right > stageRect.right + 1 ||
        r.top < stageRect.top - 1 ||
        r.bottom > stageRect.bottom + 1
      ) {
        out.push({ kind: 'outside stage', el: name });
      }
      if (cs.display !== 'inline') {
        if (el.scrollWidth > el.clientWidth + 2) {
          out.push({
            kind: 'horizontal overflow',
            el: name,
            detail: `${el.scrollWidth}>${el.clientWidth}`,
          });
        }
        // Large type often has glyphs taller than its line box. That is not a
        // layout bug unless the element actually clips (hidden/auto/scroll or
        // a fixed height). Only flag vertical overflow in that case.
        const clipsY = cs.overflowY !== 'visible' || cs.maxHeight !== 'none';
        if (clipsY && el.scrollHeight > el.clientHeight + 2) {
          out.push({
            kind: 'vertical overflow',
            el: name,
            detail: `${el.scrollHeight}>${el.clientHeight}`,
          });
        }
      }
      if (subRect && el !== sub && !el.closest('#subtitle')) {
        const ix = Math.max(0, Math.min(r.right, subRect.right) - Math.max(r.left, subRect.left));
        const iy = Math.max(0, Math.min(r.bottom, subRect.bottom) - Math.max(r.top, subRect.top));
        if (ix * iy > 40) out.push({ kind: 'overlaps subtitle', el: name });
      }
    }

    // Two independent text elements must not sit on top of each other. This is
    // the failure mode that a single screenshot of short copy hides: a wrapped
    // heading growing into the subtitle, a long note sliding under a table, etc.
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i];
        const b = items[j];
        if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
        if (a.el === sub || b.el === sub) continue;
        const ix = Math.max(0, Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left));
        const iy = Math.max(0, Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top));
        const overlap = ix * iy;
        const smaller = Math.min(a.r.width * a.r.height, b.r.width * b.r.height);
        if (overlap > Math.max(120, smaller * 0.15)) {
          out.push({ kind: 'text overlap', el: `${a.name} / ${b.name}` });
        }
      }
    }
    return out;
  });

  for (const issue of found) {
    const key = `${issue.kind}|${issue.el}`;
    if (!issues.has(key)) issues.set(key, { ...issue, firstSeen: t });
  }
}

await browser.close();

if (timingProblems.length) {
  console.error(`timing problems: ${[...new Set(timingProblems)].slice(0, 10).join('; ')}`);
  process.exit(1);
}

if (!issues.size) {
  console.log(`layout ok: ${Math.ceil((total - 0.6) / step) + 1} samples, ${total.toFixed(1)}s`);
  process.exit(0);
}

console.error(`layout issues: ${issues.size}`);
for (const issue of issues.values()) {
  const detail = issue.detail ? ` (${issue.detail})` : '';
  console.error(`  t=${issue.firstSeen.toFixed(1)}s  ${issue.kind}: ${issue.el}${detail}`);
}
process.exit(warnOnly ? 0 : 1);
