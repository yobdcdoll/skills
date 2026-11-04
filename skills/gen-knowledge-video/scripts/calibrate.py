#!/usr/bin/env python3
"""Measure the actual speaking rate of a voice and estimate narration budgets.

Usage (from the lesson directory):
    python3 calibrate.py
    python3 calibrate.py --voice en-US-AriaNeural --rate -8% --pitch 0Hz --lang en-US

Reads preset/voice/rate/pitch/lang/speed from script.json when present. Synthesizes
one standard sample, applies the same speed factor build_audio.py uses, measures
its duration with ffprobe, and prints:
  - characters per second (including punctuation)
  - CJK characters per second, or words per second for space-delimited languages
  - narration budgets for 4/6/8/10/12/15/18 minute lessons

This is a planning aid. Re-run it whenever the voice, rate, pitch or language
changes; do not reuse a Chinese rate for an English voice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import edge_tts
except ImportError:
    sys.exit("edge-tts is not installed. Run: python3 -m pip install edge-tts")

from voice_presets import resolve_voice

SAMPLES = {
    "zh-CN": (
        "哈希表的核心是把键映射到一个下标。先算哈希，再取模，得到桶的位置。"
        "如果桶是空的，直接放入；如果已经有元素，就比较键，相等就覆盖。"
    ),
    "en-US": (
        "A hash table maps a key to an index. It computes a hash, then takes a "
        "modulus to find the bucket. If the bucket is empty, the entry goes in "
        "directly. If it already has elements, the keys are compared."
    ),
    "ja-JP": (
        "ハッシュ表はキーをインデックスに変換します。まずハッシュを計算し、"
        "剰余でバケットを決めます。バケットが空ならそのまま格納します。"
    ),
}


def is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3040 <= code <= 0x30FF       # kana
        or 0x3400 <= code <= 0x9FFF    # Han
        or 0xF900 <= code <= 0xFAFF    # compatibility ideographs
    )


def count_units(text: str) -> tuple[int, int]:
    """Return (cjk_chars, words_or_zero)."""
    cjk = sum(1 for ch in text if is_cjk(ch))
    words = 0 if cjk else len(text.split())
    return cjk, words


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(out.decode().strip())


async def synth(text: str, voice: str, rate: str, pitch: str, out: Path) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    with out.open("wb") as fh:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("no audio received")


def load_defaults() -> dict:
    path = Path("script.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warning: could not read script.json: {exc}", file=sys.stderr)
        return {}


async def main() -> None:
    meta = load_defaults()
    lang = meta.get("lang", "zh-CN")
    try:
        voice, rate, pitch = resolve_voice(meta, lang)
    except ValueError as exc:
        sys.exit(str(exc))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default=voice)
    parser.add_argument("--rate", default=rate)
    parser.add_argument("--pitch", default=pitch)
    parser.add_argument("--lang", default=lang)
    parser.add_argument("--sample", help="text to synthesize instead of the built-in sample")
    parser.add_argument(
        "--speed", type=float, default=float(meta.get("speed", 1.24)),
        help="narration speed used by build_audio.py (default 1.24)"
    )
    parser.add_argument(
        "--lead", type=float, default=float(meta.get("lead", 0.8)),
        help="seconds of silence at the start (default 0.8)"
    )
    parser.add_argument(
        "--tail", type=float, default=float(meta.get("tail", 0.8)),
        help="seconds of silence at the end (default 0.8)"
    )
    parser.add_argument(
        "--gap", type=float, default=float(meta.get("gap", 0.35)),
        help="seconds between segments (default 0.35)"
    )
    args = parser.parse_args()

    sample = args.sample or SAMPLES.get(args.lang)
    if not sample:
        sample = SAMPLES["zh-CN"]
        print(
            f"no built-in sample for {args.lang}; using the Chinese sample. "
            "Pass --sample to calibrate another language.",
            file=sys.stderr,
        )

    cjk, words = count_units(sample)
    unit_name = "汉字" if cjk else "词"
    units = cjk or words

    with tempfile.TemporaryDirectory(prefix="calibrate-") as tmp:
        mp3 = Path(tmp) / "sample.mp3"
        try:
            await synth(sample, args.voice, args.rate, args.pitch, mp3)
        except Exception as exc:
            sys.exit(f"TTS failed: {exc}")
        duration = probe_duration(mp3)

    if not 0.5 <= args.speed <= 2.0:
        sys.exit("speed must be between 0.5 and 2.0 (atempo range)")
    # build_audio.py applies atempo; atempo changes duration exactly by 1/speed.
    duration /= args.speed

    total_chars = len(sample)
    char_rate = total_chars / duration
    unit_rate = units / duration
    # Budget assumes a 7-slot lesson: lead + tail + 6 gaps.
    overhead = args.lead + args.tail + args.gap * 6

    print()
    print(f"preset     {meta.get('preset') or '(language default)'}")
    print(f"voice      {args.voice}")
    print(f"rate/pitch {args.rate} / {args.pitch}")
    print(f"atempo     {args.speed:.2f}x (applied by build_audio.py)")
    print(f"lang       {args.lang}")
    print(f"sample     {total_chars} chars, {units} {unit_name}, {duration:.2f}s")
    print(f"speed      {char_rate:.2f} chars/s (with punctuation), "
          f"{unit_rate:.2f} {unit_name}/s")
    print()
    print("narration budget (already subtracts lead/tail/6 gaps):")
    print(f"{'minutes':>7}  {'chars':>7}  {unit_name:>6}")
    for minutes in (4, 6, 8, 10, 12, 15, 18):
        speaking = max(0.0, minutes * 60 - overhead)
        print(f"{minutes:>7}  {round(speaking * char_rate):>7}  "
              f"{round(speaking * unit_rate):>6}")
    print()
    print("Use these numbers as a starting point, then re-measure after the script is written.")


if __name__ == "__main__":
    asyncio.run(main())
