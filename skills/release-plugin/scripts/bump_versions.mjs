#!/usr/bin/env node
// Bump a skill and the plugin bundle that ships it.
//
// Usage (from anywhere in the repo):
//   node <skill>/scripts/bump_versions.mjs --skill gen-knowledge-video
//   node <skill>/scripts/bump_versions.mjs --skill gen-knowledge-video \
//        --skill-version 1.4.0 --bundle-version 2.3.0
//   ... --dry-run
//
// Defaults: patch bump both versions. Updates every manifest Claude Code and
// Cursor read, so `claude plugin update` actually sees a new bundle version.

import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};
const dryRun = args.includes('--dry-run');
const skillName = opt('--skill');
if (!skillName) {
  console.error('usage: node bump_versions.mjs --skill <name> [--skill-version x.y.z] [--bundle-version x.y.z] [--root <repo>] [--dry-run]');
  process.exit(2);
}

function die(msg) {
  console.error(`✗ ${msg}`);
  process.exit(1);
}

function findRoot(start) {
  let cur = path.resolve(start);
  for (;;) {
    if (fs.existsSync(path.join(cur, '.claude-plugin/plugin.json'))) return cur;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  die(`repo root not found from ${start} (no .claude-plugin/plugin.json)`);
}

const root = path.resolve(opt('--root', findRoot(process.cwd())));
const rel = p => path.relative(root, p) || '.';
const readJson = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const changed = [];

function write(p, content) {
  changed.push(rel(p));
  if (!dryRun) fs.writeFileSync(p, content);
}
function writeJson(p, obj) {
  write(p, JSON.stringify(obj, null, 2) + '\n');
}

function parseVersion(v) {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(v || '').trim());
  if (!m) die(`invalid semver: ${JSON.stringify(v)}`);
  return m.slice(1).map(Number);
}
function bumpPatch(v) {
  const [a, b, c] = parseVersion(v);
  return `${a}.${b}.${c + 1}`;
}

// --- skill version ---
const skillDir = path.join(root, 'skills', skillName);
const skillMdPath = path.join(skillDir, 'SKILL.md');
if (!fs.existsSync(skillMdPath)) die(`skill not found: ${rel(skillMdPath)}`);

const skillMd = fs.readFileSync(skillMdPath, 'utf8');
const fm = /^---\r?\n([\s\S]*?)\r?\n---/.exec(skillMd);
if (!fm) die(`${rel(skillMdPath)} has no frontmatter`);
const verLine = /^(\s*version:\s*)([^\r\n]+)\s*$/m.exec(fm[1]);
if (!verLine) die(`${rel(skillMdPath)} frontmatter has no version`);
const currentSkill = verLine[2].trim();
const nextSkill = opt('--skill-version', bumpPatch(currentSkill));

if (nextSkill !== currentSkill) {
  const newFm = fm[1].replace(verLine[0], `${verLine[1]}${nextSkill}`);
  write(skillMdPath, skillMd.replace(fm[1], newFm));
}

for (const p of [
  path.join(skillDir, '.claude-plugin', 'plugin.json'),
  path.join(skillDir, '.cursor-plugin', 'plugin.json'),
]) {
  if (!fs.existsSync(p)) continue;
  const j = readJson(p);
  if (j.version === nextSkill) continue;
  j.version = nextSkill;
  writeJson(p, j);
}

// --- bundle version ---
const rootPluginPath = path.join(root, '.claude-plugin', 'plugin.json');
const rootPlugin = readJson(rootPluginPath);
const bundleName = rootPlugin.name;
const currentBundle = rootPlugin.version;
const nextBundle = opt('--bundle-version', bumpPatch(currentBundle));

for (const p of [
  rootPluginPath,
  path.join(root, '.cursor-plugin', 'plugin.json'),
]) {
  const j = readJson(p);
  if (j.version === nextBundle) continue;
  j.version = nextBundle;
  writeJson(p, j);
}

// --- Cursor marketplace: skill entry + metadata + bundle entry ---
const cursorMpPath = path.join(root, '.cursor-plugin', 'marketplace.json');
if (fs.existsSync(cursorMpPath)) {
  const mp = readJson(cursorMpPath);
  const before = JSON.stringify(mp);
  const entry = (mp.plugins || []).find(p => p.name === skillName);
  if (!entry) die(`.cursor-plugin/marketplace.json has no entry named "${skillName}"`);
  entry.version = nextSkill;
  if (mp.metadata) mp.metadata.version = nextBundle;
  const bundle = (mp.plugins || []).find(p => p.name === bundleName);
  if (bundle) bundle.version = nextBundle;
  if (JSON.stringify(mp) !== before) writeJson(cursorMpPath, mp);
}

console.log(`${dryRun ? '(dry run) ' : ''}skill  ${skillName}: ${currentSkill} -> ${nextSkill}`);
console.log(`${dryRun ? '(dry run) ' : ''}bundle ${bundleName}: ${currentBundle} -> ${nextBundle}`);
if (changed.length) {
  console.log('updated:');
  for (const f of changed) console.log(`  ${f}`);
} else {
  console.log('no files changed (versions already at target)');
}
