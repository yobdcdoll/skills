#!/usr/bin/env node
/**
 * Render an exact frame range from scene.html.
 *
 * Usage (from the lesson directory):
 *   node render_range.mjs <startFrame> <endFrame> <fps>
 *
 * Each frame i is rendered at t = i / fps via window.renderAt(t), so the output
 * has no dependency on wall-clock time or machine load. This is what makes
 * audio/video sync deterministic.
 *
 * Environment:
 *   SCENE=scene.html     scene file
 *   BROWSER_PATH=...     explicit Chrome/Edge/Chromium binary
 *   WIDTH=1920           viewport width  (scene.html must match)
 *   HEIGHT=1080          viewport height (scene.html must match)
 *   QUALITY=90           JPEG quality
 *
 * Browser resolution order:
 *   BROWSER_PATH -> macOS/Linux/Windows Edge/Chrome/Chromium -> Playwright Chromium
 *
 * Playwright is resolved from the current working directory's node_modules, so
 * running this script from a skill directory still uses the lesson's install.
 */

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [start, end, fps] = process.argv.slice(2).map(Number);
if (![start, end, fps].every(Number.isFinite) || end <= start || fps <= 0) {
  console.error('usage: node render_range.mjs <startFrame> <endFrame> <fps>');
  process.exit(2);
}

const width = Number(process.env.WIDTH) || 1920;
const height = Number(process.env.HEIGHT) || 1080;
const quality = Number(process.env.QUALITY) || 90;

const requireFromCwd = createRequire(path.join(process.cwd(), 'package.json'));

let chromium;
try {
  ({ chromium } = requireFromCwd('playwright'));
} catch (err) {
  try {
    ({ chromium } = requireFromCwd('playwright-core'));
  } catch {
    console.error(
      'playwright not found. From the lesson directory run:\n' +
        '  npm i playwright && npx playwright install chromium\n' +
        'or install playwright-core and set BROWSER_PATH to Chrome/Edge.\n' +
        'The same command works on macOS, Linux and Windows.'
    );
    process.exit(2);
  }
}

const browserCandidates = [
  process.env.BROWSER_PATH,
  // macOS
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  // Linux
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/snap/bin/chromium',
  '/usr/bin/microsoft-edge',
  // Windows
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  process.env.LOCALAPPDATA &&
    path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe'),
  process.env.LOCALAPPDATA &&
    path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
].filter(Boolean);
const executablePath = browserCandidates.find((p) => fs.existsSync(p));

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

fs.mkdirSync('frames', { recursive: true });

const browser = await chromium.launch(launchOptions);
const page = await browser.newPage({
  viewport: { width, height },
  deviceScaleFactor: 1,
});

const problems = [];
page.on('console', (msg) => {
  const text = msg.text();
  if (/missing cue|no cues for segment/i.test(text)) {
    problems.push(text);
  }
});
page.on('pageerror', (err) => {
  problems.push(`pageerror: ${err.message}`);
});

await page.goto(pathToFileURL(scenePath).href);
await page.evaluate(() => document.fonts.ready);
await page.waitForFunction(() => typeof window.renderAt === 'function');
await page.waitForTimeout(300);

// These three files are the single source of timing. If any is missing the
// scene renders every beat at t=0 and silently produces a broken video.
const assets = await page.evaluate(() => ({
  timeline: !!window.TIMELINE,
  cues: !!window.CUES,
  subtitles: !!window.SUBTITLES,
}));
const missingAssets = Object.entries(assets)
  .filter(([, ok]) => !ok)
  .map(([name]) => name);
if (missingAssets.length) {
  console.error(
    `missing scene data: ${missingAssets.join(', ')}. ` +
      'Run build_audio.py and build_subtitles.mjs first.'
  );
  await browser.close();
  process.exit(1);
}

for (let i = start; i < end; i++) {
  const t = i / fps;
  await page.evaluate((time) => window.renderAt(time), t);
  await page.screenshot({
    path: path.join('frames', `f${String(i).padStart(5, '0')}.jpg`),
    type: 'jpeg',
    quality,
  });
  if (i % 500 === 0) console.log(`${i}/${end}`);
  // Fail fast: a missing cue means every later beat may be wrong, so there is
  // no point burning CPU on the rest of this shard.
  if (problems.length) break;
}

await browser.close();

if (problems.length) {
  const unique = [...new Set(problems)].slice(0, 10);
  console.error(
    `render failed: ${problems.length} timing problem(s):\n  ` + unique.join('\n  ')
  );
  process.exit(1);
}

console.log(`done ${start}-${end}`);
