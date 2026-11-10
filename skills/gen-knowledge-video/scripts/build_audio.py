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

Pronunciation:
    In segment text, 〖display|spoken〗 fixes a reading without changing what
    viewers read. Example: `第 3 〖行|航〗` displays 行 but sends 航 (háng) to TTS;
    `〖JSON|杰森〗` displays JSON but speaks "杰森". Every occurrence must be
    annotated. Cue/timeline text always uses the display side.
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
KIND = DATA.get("kind", "concept")

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

# 〖display|spoken〗 fixes a pronunciation without changing subtitles or visuals.
# Display text is what viewers read; spoken text is the only thing sent to TTS.
ANNOTATION = re.compile(r"〖([^〖〗|]+)\|([^〖〗|]+)〗")


def split_sentences(text: str) -> list[str]:
    """Split like Edge TTS SentenceBoundary: 。！？!? and newlines, not ，、；：…."""
    parts = re.findall(r"[^。！？!?\r\n]+[。！？!?]*", text)
    return [p.strip() for p in parts if p.strip()]


def sentence_marks(text: str) -> list[str]:
    return re.findall(r"[。！？!?\r\n]", text)


def prepare_narration(raw: str, seg_id: str) -> tuple[str, str, list[str]]:
    display = ANNOTATION.sub(lambda m: m.group(1), raw)
    spoken = ANNOTATION.sub(lambda m: m.group(2), raw)
    for label, value in (("display", display), ("spoken", spoken)):
        if "〖" in value or "〗" in value:
            sys.exit(
                f"segment {seg_id}: malformed pronunciation annotation in {label} text; "
                "use 〖display|spoken〗 with non-empty sides"
            )
    if sentence_marks(display) != sentence_marks(spoken):
        sys.exit(
            f"segment {seg_id}: pronunciation annotation changed sentence punctuation; "
            "keep 。！？!? and newlines outside 〖display|spoken〗"
        )
    return display, spoken, split_sentences(display)


# Common in tech narration; TTS still guesses wrong often enough to gate.
ZH_PRONUNCIATION_RISKS = [
    (
        re.compile(
            r"第\s*[0-9一二三四五六七八九十百千]+\s*行|[0-9]+\s*行|"
            r"行号|行数|行首|行尾|行内|行间|行列|银行|行业|"
            r"当前行|所在行|目标行|首行|末行|整行|逐行|换行|空行|"
            r"每一行|上一行|下一行|这一行|每行|单行|多行|一行|两行"
        ),
        "行 = row 时读 háng",
    ),
    (
        re.compile(
            r"重新|重复|重启|重试|重排|重载|重传|重入|重写|重定向|"
            r"重置|重建|重组|重叠|重放|重连|重发|重算|重命名|重编码|"
            r"重采样|重计算|重来|重开|重登|重做"
        ),
        "重 = again 时读 chóng",
    ),
    (
        re.compile(r"(?<![A-Za-z])[Jj][Ss][Oo][Nn](?![A-Za-z])"),
        "JSON 读「杰森」，不要逐字母念",
    ),
]


def check_pronunciation(raw: str, seg_id: str) -> None:
    # Language lessons discuss readings explicitly; the generic gate would be noise.
    if not LANG.startswith("zh") or KIND == "language":
        return
    scan = ANNOTATION.sub("", raw)
    hits: list[tuple[str, str]] = []
    for pattern, hint in ZH_PRONUNCIATION_RISKS:
        for match in pattern.finditer(scan):
            item = (match.group(0), hint)
            if item not in hits:
                hits.append(item)
    if hits:
        detail = "；".join(f"{token}（{hint}）" for token, hint in hits)
        sys.exit(
            f"segment {seg_id}: unannotated pronunciation risk: {detail}. "
            "Annotate every occurrence as 〖display|spoken〗, e.g. "
            "第 3 〖行|航〗、〖重新|虫新〗、〖JSON|杰森〗；见 SKILL.md 2.3"
        )


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
    _display, _spoken, _display_sentences = prepare_narration(
        str(_seg.get("text", "")), _sid
    )
    check_pronunciation(str(_seg.get("text", "")), _sid)
    _seg["_display"] = _display
    _seg["_spoken"] = _spoken
    _seg["_display_sentences"] = _display_sentences


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
    communicate = edge_tts.Communicate(seg["_spoken"], VOICE, rate=RATE, pitch=PITCH)
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
            sentences = fallback_sentences(seg["_display"], duration)
        elif seg["_spoken"] != seg["_display"]:
            # Cue text drives subtitles. Restore the written form so viewers see
            # JSON/行/重新, not the homophones used only to steer the TTS voice.
            if len(sentences) != len(seg["_display_sentences"]):
                sys.exit(
                    f"segment {seg['id']}: TTS returned {len(sentences)} sentence "
                    f"boundaries for {len(seg['_display_sentences'])} written sentences; "
                    "shorten the segment or keep sentence punctuation identical"
                )
            for ev, written in zip(sentences, seg["_display_sentences"]):
                ev["text"] = written

        cues[seg["id"]] = {"words": words, "sentences": sentences}

        timeline.append(
            {
                "id": seg["id"],
                "label": seg.get("label", seg["id"]),
                "text": seg["_display"],
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
