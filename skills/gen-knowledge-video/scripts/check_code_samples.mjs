#!/usr/bin/env node
// Code-lesson gate: a lesson marked {"kind":"code"} must actually show code.
//
// Usage (from the lesson directory):
//   node <skill>/scripts/check_code_samples.mjs [lesson-dir]
//
// It reads script.json + scene.html + code-plan.md and fails when:
//   - there is no code-plan.md, or a required section is missing;
//   - there is no <pre class="code"> block;
//   - a block has more than 14 non-empty lines or fewer than 3;
//   - no block has 5–14 non-empty lines (the main block);
//   - a block does not declare data-segment (so it is not tied to narration);
//   - no line declares data-cue (so highlighting cannot follow the narration);
//   - a code block uses an ellipsis/omitted-lines placeholder (the whole sample
//     must be visible, not a fragment);
//   - no code block sits in an example/how/apply/demo/practice segment;
//   - there is no non-empty <pre class="code-out"> output block;
//   - an output block is not bound to a code block via data-for.
//
// Semantic completeness (every identifier declared, entry point visible,
// thread/async creation shown), determinism, and exact output/code
// correspondence cannot be checked statically. The gate only enforces structure
// and binding; the QA pass must confirm the sample stands on its own and rerun
// it to compare output.
//
// The goal is not to prove the code compiles. It is to stop the "talk only,
// no sample" failure mode: no visible code + real output means no delivery.

import fs from 'node:fs';
import path from 'node:path';

const dir = path.resolve(process.argv[2] || '.');
const scriptPath = path.join(dir, 'script.json');
const scenePath = path.join(dir, 'scene.html');

function die(msg, code = 2) {
  console.error(msg);
  process.exit(code);
}

if (!fs.existsSync(scriptPath)) die(`missing ${scriptPath}`, 2);
if (!fs.existsSync(scenePath)) die(`missing ${scenePath} (run from the lesson directory)`, 2);

const script = JSON.parse(fs.readFileSync(scriptPath, 'utf8'));
const kind = script.kind || 'concept';
const isCode = kind === 'code';

const html = fs.readFileSync(scenePath, 'utf8');

const attrsOf = tag => {
  const out = {};
  const re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/g;
  let m;
  while ((m = re.exec(tag))) out[m[1].toLowerCase()] = m[3] ?? m[4] ?? m[5] ?? '';
  return out;
};
const classesOf = attrs => (attrs.class || '').split(/\s+/).filter(Boolean);

const decode = s => s
  .replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"')
  .replace(/&#39;|&apos;/g, "'")
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&');

const stripTags = s => decode(s.replace(/<[^>]*>/g, ''));

// Extract the text of each line. Templates use one <span class="cl"> per code
// line; plain <pre> text with newlines is accepted as a fallback.
function linesOf(inner) {
  const starts = [];
  const openRe = /<span\b[^>]*>/gi;
  let m;
  while ((m = openRe.exec(inner))) {
    const attrs = attrsOf(m[0]);
    if (classesOf(attrs).includes('cl')) {
      starts.push({ contentStart: openRe.lastIndex, tagStart: m.index });
    }
  }
  if (starts.length === 0) {
    return inner.split(/\r?\n/).map(stripTags).map(s => s.trim()).filter(Boolean);
  }
  const lines = [];
  for (let i = 0; i < starts.length; i++) {
    const from = starts[i].contentStart;
    const to = i + 1 < starts.length ? starts[i + 1].tagStart : inner.length;
    const text = stripTags(inner.slice(from, to)).trim();
    if (text) lines.push(text);
  }
  return lines;
}

const preRe = /<pre\b([^>]*)>([\s\S]*?)<\/pre>/gi;
const codeBlocks = [];
const outputBlocks = [];
let m;
while ((m = preRe.exec(html))) {
  const attrs = attrsOf(m[1]);
  const classes = classesOf(attrs);
  if (classes.includes('code')) {
    codeBlocks.push({ attrs, inner: m[2], id: attrs.id || '(no id)' });
  } else if (classes.includes('code-out')) {
    outputBlocks.push({ attrs, inner: m[2], id: attrs.id || '(no id)' });
  }
}

if (!isCode) {
  if (codeBlocks.length > 0) {
    console.warn(`warning: scene.html has ${codeBlocks.length} <pre class="code"> block(s), but script.json kind is "${kind}". Set "kind": "code" so the code gate actually runs.`);
  }
  process.exit(0);
}

const errors = [];

// code-plan.md is the paper trail for semantic completeness: which identifiers
// are declared, where the entry point is, how threads/async are created. The
// gate checks that the sections exist; QA checks their content.
const planPath = path.join(dir, 'code-plan.md');
if (!fs.existsSync(planPath)) {
  errors.push('missing code-plan.md; a code lesson must plan declarations/types, entry, thread/async, output, and a variant before narration.');
} else {
  const plan = fs.readFileSync(planPath, 'utf8');
  const requiredSections = [
    ['声明与类型', /^#{1,6}\s*.*(?:声明|类型|declaration|type)/im],
    ['入口', /^#{1,6}\s*.*(?:入口|entry|\bmain\b)/im],
    ['线程与异步', /^#{1,6}\s*.*(?:线程|异步|回调|thread|async|callback)/im],
    ['输出', /^#{1,6}\s*.*(?:输出|output)/im],
    ['变式与边界', /^#{1,6}\s*.*(?:变式|边界|variant|boundary)/im],
  ];
  const missing = requiredSections.filter(([, re]) => !re.test(plan)).map(([name]) => name);
  if (missing.length) {
    errors.push(`code-plan.md is missing section(s): ${missing.join(', ')}. Use ## headings: 声明与类型 / 入口 / 线程与异步 / 输出 / 变式与边界.`);
  }
}

const segmentRole = new Map();
for (const seg of (script.segments || [])) segmentRole.set(seg.id, seg.role || seg.id);
const exampleLike = new Set(['example', 'how', 'apply', 'demo', 'practice']);

if (codeBlocks.length === 0) {
  errors.push('no <pre class="code"> block. A code lesson must show the snippet itself, not just describe it.');
}

// A fragment hidden behind "..." / // 省略 is still a fragment. Spread
// operators (`...args`) are fine because the line is not only an ellipsis.
const placeholderRe = /^(?:\.\.\.|…)$|^(?:\/\/|#|\/\*|\*).*(?:\.{3}|…|省略|其余略|下略)/;

let exampleBlock = false;
let mainBlock = false;
for (const block of codeBlocks) {
  const lines = linesOf(block.inner);
  for (const line of lines) {
    if (placeholderRe.test(line)) {
      errors.push(`code block "${block.id}" has an omitted-lines placeholder (${JSON.stringify(line)}); show the complete sample instead of a fragment.`);
    }
  }
  if (lines.length < 3) {
    errors.push(`code block "${block.id}" has ${lines.length} non-empty line(s); even a companion block needs at least 3 lines and must be a complete unit.`);
  } else if (lines.length > 14) {
    errors.push(`code block "${block.id}" has ${lines.length} non-empty lines; split it into 2 scenes (max 14 per screen).`);
  } else if (lines.length >= 5) {
    mainBlock = true;
  }

  const segment = block.attrs['data-segment'];
  if (!segment) {
    errors.push(`code block "${block.id}" is missing data-segment; set it to the script segment id (usually "example").`);
  } else {
    const role = segmentRole.get(segment);
    if (!role) {
      errors.push(`code block "${block.id}" points at data-segment="${segment}", but script.json has no such segment.`);
    } else if (exampleLike.has(role) || exampleLike.has(segment)) {
      exampleBlock = true;
    }
  }

  if (!/\bdata-cue\s*=/.test(block.inner)) {
    errors.push(`code block "${block.id}" has no data-cue lines; tie each line to the narration cue that should highlight it.`);
  }
}

if (codeBlocks.length > 0 && !mainBlock) {
  errors.push('no block has 5–14 non-empty lines; each scene needs one main block with full context (companion blocks may be 3–4 lines).');
}

if (codeBlocks.length > 0 && !exampleBlock) {
  errors.push('no code block sits in an example/how/apply/demo segment; the sample must be part of the teaching, not an appendix.');
}

const outputs = outputBlocks.filter(b => stripTags(b.inner).trim());
if (outputs.length === 0) {
  errors.push('no non-empty <pre class="code-out"> block; show the real output (or a run/terminal capture) next to the code.');
}

for (const out of outputs) {
  const target = out.attrs['data-for'];
  if (!target) {
    errors.push(`output block "${out.id}" is missing data-for; bind it to the id of the code block it prints so the two cannot drift apart.`);
  } else if (!codeBlocks.some(b => b.attrs.id === target)) {
    errors.push(`output block "${out.id}" has data-for="${target}", but no code block has that id.`);
  }
}

// Self-contained video: warn (do not fail) when narration points viewers away.
const external = /(源码|完整代码|代码|项目).{0,12}(见|在|放到|放在).{0,12}(github|gitlab|gitee|仓库|课程页|简介|评论区)/i;
for (const seg of (script.segments || [])) {
  if (external.test(seg.text || '')) {
    console.warn(`warning: segment "${seg.id}" points viewers to an external source; put the code in the video instead.`);
  }
}

if (errors.length) {
  console.error('✗ code lesson check failed:');
  for (const e of errors) console.error(`  - ${e}`);
  console.error('\nSee references/code-scene-template.html for the expected structure.');
  process.exit(1);
}

const totalLines = codeBlocks.reduce((n, b) => n + linesOf(b.inner).length, 0);
console.log(`✓ code lesson OK: ${codeBlocks.length} block(s), ${totalLines} code line(s), ${outputs.length} output block(s).`);
