#!/usr/bin/env node
/**
 * Build subtitle cues and an SRT from cues.json + timeline.json.
 *
 * Usage (from the lesson directory):
 *   node build_subtitles.mjs
 *
 * Outputs:
 *   cues.js        window.CUES = {...}       scene renderers use this
 *   subtitles.js   window.SUBTITLES = [...]  burned-in subtitle renderer uses this
 *   <id>.srt       external subtitles
 *
 * Sentence boundaries from the TTS/alignment step are exact. Splitting a long
 * sentence into subtitle chunks is done proportionally by character count,
 * which is accurate enough inside a sentence and never accumulates across
 * sentences.
 *
 * Character limits come from script.json:
 *   "subtitle": { "max_cjk": 32, "max_latin": 42 }
 */

import fs from 'node:fs';
import path from 'node:path';

const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const cues = read('cues.json');
const timeline = read('timeline.json');
const meta = fs.existsSync('script.json') ? read('script.json') : {};
const base = meta.id || timeline.id || 'lesson';
const LANG = meta.lang || timeline.lang || 'zh-CN';

fs.writeFileSync('cues.js', 'window.CUES=' + JSON.stringify(cues) + ';');

// Han + Japanese kana. Korean uses spaces, so the Latin branch handles it.
const CJK = /[぀-ヿ㐀-鿿豈-﫿]/;
const ZH_MAX = Number(meta.subtitle?.max_cjk) || 32;
const EN_MAX = Number(meta.subtitle?.max_latin) || 42;

const segmenter =
  typeof Intl.Segmenter === 'function'
    ? new Intl.Segmenter(LANG, { granularity: 'word' })
    : null;

// Prefer a real word boundary over a hard character cut when a clause has no
// punctuation. If Intl.Segmenter is unavailable, fall back to the old cut.
function wordBoundaryCut(text, max) {
  if (!segmenter) return -1;
  let best = -1;
  for (const part of segmenter.segment(text)) {
    if (part.index > max) break;
    if (part.index > 0 && part.index >= max * 0.6) best = part.index;
  }
  return best;
}

function splitEnglish(part, max) {
  const out = [];
  const words = part.split(/\s+/).filter(Boolean);
  let line = '';
  for (const word of words) {
    if (word.length > max) {
      if (line) {
        out.push(line);
        line = '';
      }
      for (let i = 0; i < word.length; i += max) out.push(word.slice(i, i + max));
      continue;
    }
    const next = line ? `${line} ${word}` : word;
    if (next.length > max && line) {
      out.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) out.push(line);
  return out;
}

function splitText(text, max = ZH_MAX) {
  const trimmed = text.trim();
  if (!trimmed) return [];

  // Keep punctuation attached to the preceding clause.
  const parts = trimmed.match(/[^，。；：！？、,.!?;:]+[，。；：！？、,.!?;:]*/g) || [trimmed];
  const out = [];

  for (const raw of parts) {
    const part = raw.trim();
    if (!part) continue;

    if (!CJK.test(part)) {
      out.push(...splitEnglish(part, EN_MAX));
      continue;
    }

    let rest = part;
    while (rest.length > max) {
      let cut = -1;
      for (const p of ['，', '、', '；', '：', '。', '！', '？', ',', ';', ':', '!', '?']) {
        const i = rest.lastIndexOf(p, max);
        if (i > cut) cut = i;
      }
      if (cut < max * 0.5) {
        const w = wordBoundaryCut(rest, max);
        cut = w > 0 ? w - 1 : max - 1;
      }
      out.push(rest.slice(0, cut + 1));
      rest = rest.slice(cut + 1).trimStart();
    }
    if (rest) out.push(rest);
  }

  return out;
}

const subs = [];
for (const seg of timeline.segments) {
  const segmentCues = cues[seg.id]?.sentences || [];
  if (!segmentCues.length) {
    console.warn(`no cues for segment ${seg.id}; no subtitles for this segment`);
  }
  for (const sentence of segmentCues) {
    const chunks = splitText(sentence.text);
    if (!chunks.length) continue;

    const totalChars = chunks.reduce((n, c) => n + c.length, 0) || 1;
    const sentenceDur = Math.max(0, sentence.end - sentence.start);
    let offset = 0;

    for (const chunk of chunks) {
      const dur = (sentenceDur * chunk.length) / totalChars;
      const start = seg.start + sentence.start + offset;
      const end = start + dur;
      subs.push({
        start: Number(start.toFixed(3)),
        end: Number(end.toFixed(3)),
        text: chunk,
      });
      offset += dur;
    }
  }
}

subs.sort((a, b) => a.start - b.start);

// Guard against accidental overlaps; trimming the previous cue is safer than
// letting two subtitles render at once.
for (let i = 1; i < subs.length; i++) {
  if (subs[i].start < subs[i - 1].end) {
    const overlap = subs[i - 1].end - subs[i].start;
    // TTS sentence boundaries commonly overlap by ~50 ms; that is harmless.
    if (overlap > 0.08) {
      console.warn(
        `overlap ${overlap.toFixed(3)}s: "${subs[i - 1].text}" -> "${subs[i].text}"`
      );
    }
    subs[i - 1].end = Number(subs[i].start.toFixed(3));
  }
  if (subs[i].end <= subs[i].start) {
    console.warn(`zero-length cue: "${subs[i].text}"`);
    subs[i].end = Number((subs[i].start + 0.2).toFixed(3));
  }
}

fs.writeFileSync('subtitles.js', 'window.SUBTITLES=' + JSON.stringify(subs) + ';');

const pad = (n, w = 2) => String(n).padStart(w, '0');
function srtTime(t) {
  const msTotal = Math.max(0, Math.round(t * 1000));
  const h = Math.floor(msTotal / 3_600_000);
  const m = Math.floor((msTotal % 3_600_000) / 60_000);
  const s = Math.floor((msTotal % 60_000) / 1000);
  const ms = msTotal % 1000;
  return `${pad(h)}:${pad(m)}:${pad(s)},${pad(ms, 3)}`;
}

const srt = subs
  .map((s, i) => `${i + 1}\n${srtTime(s.start)} --> ${srtTime(s.end)}\n${s.text}\n`)
  .join('\n');

const srtPath = path.join(process.cwd(), `${base}.srt`);
fs.writeFileSync(srtPath, srt);

const longest = subs.reduce((a, b) => (a.text.length > b.text.length ? a : b), {
  text: '',
});
console.log(
  JSON.stringify(
    {
      lang: LANG,
      cues: subs.length,
      srt: srtPath,
      longest: longest.text.length,
      longest_text: longest.text,
      duration: timeline.total,
    },
    null,
    2
  )
);
