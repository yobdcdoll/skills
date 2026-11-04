#!/usr/bin/env python3
"""One-pass Edge TTS: audio, timeline, and sentence cues from the same synthesis.

Usage (from the lesson directory containing script.json):
    python3 build_audio.py

Why one pass:
    If audio and cue timings come from two separate TTS runs, their durations can
    differ. Visuals and subtitles then drift against the audio. Streaming once and
    keeping both the audio bytes and the SentenceBoundary events eliminates that
    whole class of bug.

Outputs:
    audio/<segment>.mp3
    audio/<segment>.wav      48 kHz mono PCM s16le
    audio/full.wav           lead + segments (gap between) + tail
    timeline.json            absolute segment starts/ends
    scene-data.js            window.TIMELINE = ...
    cues.json                per-segment sentence/word boundaries (segment-relative)

Speed:
    script.json `"speed": 1.24` (skill default) speeds narration up 1.24x with
    ffmpeg atempo, which preserves pitch. Every cue is rescaled by the *measured*
    duration ratio, not by the nominal value, so subtitles and visuals stay
    locked to the audio. Lead/gap/tail are breathing room and are not scaled.
    Set `"speed": 1.0` to keep the raw TTS pace.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    sys.exit("edge-tts is not installed. Run: python3 -m pip install edge-tts")

from voice_presets import resolve_voice

ROOT = Path.cwd()
SCRIPT = ROOT / "script.json"
if not SCRIPT.exists():
    sys.exit("script.json not found; run this script from the lesson directory")

AUDIO = ROOT / "audio"
AUDIO.mkdir(exist_ok=True)

DATA = json.loads(SCRIPT.read_text(encoding="utf-8"))
LANG = DATA.get("lang", "zh-CN")

try:
    VOICE, RATE, PITCH = resolve_voice(DATA, LANG)
except ValueError as exc:
    sys.exit(str(exc))
GAP = float(DATA.get("gap", 0.35))
LEAD = float(DATA.get("lead", 0.8))
TAIL = float(DATA.get("tail", 0.8))
SPEED = float(DATA.get("speed", 1.24))
if not 0.5 <= SPEED <= 2.0:
    sys.exit("speed must be between 0.5 and 2.0 (atempo range)")

SEGMENTS = DATA.get("segments") or []
if not SEGMENTS:
    sys.exit("script.json has no segments")

_seen_ids: set[str] = set()
for _seg in SEGMENTS:
    _sid = str(_seg.get("id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", _sid):
        sys.exit(f"invalid segment id: {_sid!r}; use letters, digits, _ or -")
    if _sid in _seen_ids:
        sys.exit(f"duplicate segment id: {_sid}")
    _seen_ids.add(_sid)
    if not str(_seg.get("text", "")).strip():
        sys.exit(f"empty text for segment: {_sid}")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(out.decode().strip())


def atempo_chain(speed: float) -> str:
    """Build an atempo filter chain; one instance is only reliable in 0.5–2.0."""
    filters: list[str] = []
    s = speed
    while s > 2.0:
        filters.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        filters.append("atempo=0.5")
        s /= 0.5
    filters.append(f"atempo={s:.6f}")
    return ",".join(filters)


def scale_events(events: list[dict], ratio: float, duration: float) -> None:
    """Rescale segment-relative cue times after the audio speed changes."""
    for ev in events:
        ev["start"] = round(ev["start"] * ratio, 3)
        ev["end"] = round(min(ev["end"] * ratio, duration), 3)


def fallback_sentences(text: str, duration: float) -> list[dict]:
    """Approximate sentence timing when Edge TTS emits no SentenceBoundary."""
    parts = [p.strip() for p in re.split(r"(?<=[，。；：！？、,.!?;:])", text) if p.strip()]
    if not parts:
        parts = [text]
    total = sum(len(p) for p in parts) or 1
    cursor = 0.0
    out = []
    for part in parts:
        d = duration * len(part) / total
        out.append(
            {
                "text": part,
                "start": round(cursor, 3),
                "end": round(cursor + d, 3),
                "fallback": True,
            }
        )
        cursor += d
    return out


async def synth_once(seg: dict) -> tuple[Path, list[dict], list[dict]]:
    mp3 = AUDIO / f"{seg['id']}.mp3"
    communicate = edge_tts.Communicate(seg["text"], VOICE, rate=RATE, pitch=PITCH)
    sentences: list[dict] = []
    words: list[dict] = []
    with mp3.open("wb") as fh:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                sentences.append(
                    {
                        "text": chunk["text"],
                        "start": round(chunk["offset"] / 1e7, 3),
                        "end": round((chunk["offset"] + chunk["duration"]) / 1e7, 3),
                    }
                )
            elif chunk["type"] == "WordBoundary":
                words.append(
                    {
                        "text": chunk["text"],
                        "start": round(chunk["offset"] / 1e7, 3),
                        "end": round((chunk["offset"] + chunk["duration"]) / 1e7, 3),
                    }
                )
    if not mp3.exists() or mp3.stat().st_size == 0:
        raise RuntimeError(f"no audio for segment {seg['id']}")
    return mp3, sentences, words


async def synth(seg: dict, retries: int = 3) -> tuple[Path, list[dict], list[dict]]:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await synth_once(seg)
        except Exception as exc:  # network hiccups, NoAudioReceived, ...
            last = exc
            print(f"  retry {attempt}/{retries}: {seg['id']}: {exc}", file=sys.stderr)
            await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(f"TTS failed for {seg['id']}") from last


async def main() -> None:
    timeline = []
    cues = {}
    cursor = LEAD

    for seg in SEGMENTS:
        print(f"synth {seg['id']} ...")
        mp3, sentences, words = await synth(seg)
        wav = AUDIO / f"{seg['id']}.wav"
        source_duration = probe_duration(mp3)
        convert = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(mp3),
        ]
        if abs(SPEED - 1.0) > 1e-6:
            convert += ["-filter:a", atempo_chain(SPEED)]
        convert += [
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ]
        run(convert)
        duration = probe_duration(wav)

        # atempo is exact in duration, but the MP3 container adds padding.
        # Scale by the measured ratio so cues stay locked to the sped audio.
        if abs(SPEED - 1.0) > 1e-6 and source_duration > 0:
            ratio = duration / source_duration
            scale_events(sentences, ratio, duration)
            scale_events(words, ratio, duration)

        if not sentences:
            print(
                f"  WARNING: no SentenceBoundary for {seg['id']}; using punctuation fallback",
                file=sys.stderr,
            )
            sentences = fallback_sentences(seg["text"], duration)

        cues[seg["id"]] = {"words": words, "sentences": sentences}

        timeline.append(
            {
                "id": seg["id"],
                "label": seg.get("label", seg["id"]),
                "text": seg["text"],
                "audio": f"audio/{seg['id']}.wav",
                "start": round(cursor, 3),
                "duration": round(duration, 3),
                "end": round(cursor + duration, 3),
            }
        )
        cursor += duration + GAP

        last_end = sentences[-1]["end"] if sentences else 0.0
        if abs(last_end - duration) > 0.8:
            print(
                f"  WARNING: {seg['id']} last cue {last_end:.3f}s vs audio {duration:.3f}s",
                file=sys.stderr,
            )

    def silence(name: str, seconds: float) -> Path:
        path = AUDIO / name
        run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=mono",
                "-t",
                str(seconds),
                "-c:a",
                "pcm_s16le",
                str(path),
            ]
        )
        return path

    lead_file = silence("lead.wav", LEAD)
    gap_file = silence("gap.wav", GAP)
    tail_file = silence("tail.wav", TAIL)

    concat = [lead_file]
    for i, seg in enumerate(timeline):
        concat.append(ROOT / seg["audio"])
        if i < len(timeline) - 1:
            concat.append(gap_file)
    concat.append(tail_file)

    concat_txt = AUDIO / "concat.txt"
    concat_txt.write_text(
        "\n".join(f"file '{p.as_posix().replace(chr(39), chr(92) + chr(39))}'" for p in concat)
        + "\n",
        encoding="utf-8",
    )
    full = AUDIO / "full.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(full),
        ]
    )

    # Use the real concatenated duration, not an arithmetic estimate. A single
    # stray gap file is enough to make video and audio disagree at the tail.
    total = round(probe_duration(full), 3)

    result = {
        "id": DATA.get("id", "lesson"),
        "title": DATA.get("title", ""),
        "lang": LANG,
        "preset": DATA.get("preset"),
        "voice": VOICE,
        "rate": RATE,
        "pitch": PITCH,
        "speed": SPEED,
        "total": total,
        "lead": LEAD,
        "gap": GAP,
        "tail": TAIL,
        "segments": timeline,
    }
    (ROOT / "timeline.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "scene-data.js").write_text(
        "window.TIMELINE=" + json.dumps(result, ensure_ascii=False) + ";",
        encoding="utf-8",
    )
    (ROOT / "cues.json").write_text(
        json.dumps(cues, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "total": total,
                "segments": len(timeline),
                "speed": SPEED,
                "full_wav": str(full),
                "cues": str(ROOT / "cues.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
