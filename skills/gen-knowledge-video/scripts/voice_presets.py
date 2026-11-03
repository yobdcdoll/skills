"""Voice presets shared by build_audio.py and calibrate.py.

Edge TTS does not expose Azure's style parameter for the free endpoint, so a
"calm" preset is implemented as a stable voice + rate + pitch combination.
If the user needs Azure's `mstts:express-as style="calm"`, they must replace
the TTS layer (see references/pipeline-contract.md), not this file.
"""

from __future__ import annotations

PRESETS: dict[str, dict[str, str]] = {
    # Default for Chinese lessons: Xiaoxiao, slowed down and slightly lowered.
    "xiaoxiao-calm": {
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "-12%",
        "pitch": "-6Hz",
    },
    "xiaoxiao-default": {
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "-5%",
        "pitch": "+0Hz",
    },
    "yunxi-calm": {
        "voice": "zh-CN-YunxiNeural",
        "rate": "-10%",
        "pitch": "+0Hz",
    },
    "aria-calm": {
        "voice": "en-US-AriaNeural",
        "rate": "-8%",
        "pitch": "+0Hz",
    },
    "sonia-calm": {
        "voice": "en-GB-SoniaNeural",
        "rate": "-8%",
        "pitch": "+0Hz",
    },
    "nanami-calm": {
        "voice": "ja-JP-NanamiNeural",
        "rate": "-8%",
        "pitch": "+0Hz",
    },
}


def default_voice(lang: str) -> str:
    if lang.startswith("zh"):
        return "zh-CN-XiaoxiaoNeural"
    if lang.startswith("en"):
        return "en-US-AriaNeural"
    if lang.startswith("ja"):
        return "ja-JP-NanamiNeural"
    return "zh-CN-XiaoxiaoNeural"


def resolve_voice(data: dict, lang: str) -> tuple[str, str, str]:
    """Resolve (voice, rate, pitch) from a preset and explicit overrides.

    Explicit `voice` / `rate` / `pitch` win over the preset. An unknown preset
    is an error rather than a silent fallback.
    """
    name = data.get("preset")
    preset = PRESETS.get(name) if name else None
    if name and preset is None:
        raise ValueError(
            f"unknown voice preset: {name!r}; choose from {', '.join(sorted(PRESETS))}"
        )
    preset = preset or {}

    if lang.startswith("zh"):
        default_rate, default_pitch = "-12%", "-6Hz"
    else:
        default_rate, default_pitch = "-8%", "+0Hz"

    voice = data.get("voice") or preset.get("voice") or default_voice(lang)
    rate = data.get("rate") or preset.get("rate") or default_rate
    pitch = data.get("pitch") or preset.get("pitch") or default_pitch
    return voice, rate, pitch
