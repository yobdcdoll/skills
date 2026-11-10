#!/usr/bin/env node
// Verify the installed Claude Code plugin matches the repo and contains the
// release you just pushed.
//
// Usage:
//   node <skill>/scripts/verify_install.mjs --plugin yobdcdoll-skills@skills \
//        --skill release-plugin [--needle "some new text"] [--root <repo>]
//
// Exits 1 when the installed version, commit, skill version, or needle do not
// match. Run this after `claude plugin update`.

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

function die(msg) {
  console.error(`✗ ${msg}`);
  process.exit(2);
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
const home = opt('--home', process.env.HOME || '');
const pluginId = opt('--plugin');
const skillName = opt('--skill');
const needle = opt('--needle', '');

if (!pluginId) die('missing --plugin, e.g. --plugin yobdcdoll-skills@skills');

const problems = [];

const repoPluginPath = path.join(root, '.claude-plugin', 'plugin.json');
if (!fs.existsSync(repoPluginPath)) die(`missing ${repoPluginPath}`);
const repoPlugin = JSON.parse(fs.readFileSync(repoPluginPath, 'utf8'));

const head = (() => {
  try {
    return execSync('git rev-parse HEAD', { cwd: root, encoding: 'utf8' }).trim();
  } catch {
    return '';
  }
})();

const registryPath = path.join(home, '.claude', 'plugins', 'installed_plugins.json');
if (!fs.existsSync(registryPath)) die(`missing ${registryPath}`);
const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const entries = registry.plugins && registry.plugins[pluginId];
if (!entries || !entries.length) die(`plugin not installed: ${pluginId}`);
const installed = entries[entries.length - 1];

console.log(`plugin     ${pluginId}`);
console.log(`install    ${installed.installPath}`);

if (installed.version !== repoPlugin.version) {
  problems.push(`bundle version: repo ${repoPlugin.version}, installed ${installed.version}`);
} else {
  console.log(`bundle     ${installed.version} ✓`);
}

if (head && installed.gitCommitSha !== head) {
  problems.push(`commit: repo HEAD ${head}, installed ${installed.gitCommitSha || '(none)'}`);
} else if (head) {
  console.log(`commit     ${head.slice(0, 12)} ✓`);
}

if (skillName) {
  const repoSkillMd = path.join(root, 'skills', skillName, 'SKILL.md');
  const installedSkillMd = path.join(installed.installPath, 'skills', skillName, 'SKILL.md');
  const versionOf = p => {
    if (!fs.existsSync(p)) return null;
    const text = fs.readFileSync(p, 'utf8');
    const fm = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
    const m = fm && /^\s*version:\s*([^\r\n]+)\s*$/m.exec(fm[1]);
    return m ? m[1].trim() : null;
  };
  const repoVersion = versionOf(repoSkillMd);
  const installedVersion = versionOf(installedSkillMd);
  if (!installedVersion) {
    problems.push(`skill ${skillName}: not found in the installed plugin at ${installedSkillMd}`);
  } else if (repoVersion !== installedVersion) {
    problems.push(`skill ${skillName}: repo ${repoVersion}, installed ${installedVersion}`);
  } else {
    console.log(`skill      ${skillName} ${installedVersion} ✓`);
  }
}

if (needle) {
  const base = path.join(installed.installPath, 'skills');
  const hits = [];
  const walk = dir => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.isFile() && fs.readFileSync(p, 'utf8').includes(needle)) hits.push(p);
    }
  };
  if (fs.existsSync(base)) walk(base);
  if (!hits.length) problems.push(`needle not found in installed skills/: ${JSON.stringify(needle)}`);
  else console.log(`needle     ${JSON.stringify(needle)} ✓`);
}

const dirty = (() => {
  try {
    return execSync('git status --porcelain', { cwd: root, encoding: 'utf8' }).trim();
  } catch {
    return '';
  }
})();
if (dirty) {
  console.log('note       working tree has uncommitted changes; they are not in the installed plugin');
}

if (problems.length) {
  console.error('\n✗ install verification failed:');
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}

console.log('\n✓ installed plugin matches the repo. Restart the agent to apply plugin changes.');
