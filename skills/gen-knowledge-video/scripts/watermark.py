#!/usr/bin/env python3
"""Invisible, re-compression-resistant personal watermark for lesson videos.

How it works
------------
A 128-bit token is written into one mid-frequency DCT coefficient of every
8x8 luma block, using a key-dependent +/-1 spreading sequence. Each frame
carries the whole token, so extraction can combine hundreds of frames. The
change is far below the visibility threshold on 8-bit video (typically
44–48 dB PSNR) but survives repeated H.264 re-encoding at the same resolution.

Payload
-------
16 bytes = b"WM" + up to 12 UTF-8 bytes + CRC16. A mark longer than 12 bytes
(4 Chinese characters) must be shortened to an ID; the ID can point to a
local registry.

Key
---
The key changes the block->bit assignment and the spreading sequence. Without
it, extraction does not work; with it, the embedded text is readable. The key
is not encryption: anyone who has both the video and the key can read the mark.

Usage (from the lesson directory)
---------------------------------
    # embed into rendered frames before the final ffmpeg encode (recommended)
    python3 <skill>/scripts/watermark.py embed-frames --frames frames --config watermark.json

    # embed into an already encoded MP4 (re-encodes video at CRF 18)
    python3 <skill>/scripts/watermark.py embed-video --video lesson.mp4 --out lesson-wm.mp4 --config watermark.json

    # verify
    python3 <skill>/scripts/watermark.py extract --video lesson.mp4 --key "your-secret"

watermark.json:
    { "mark": "yobdcdoll", "key": "replace-with-a-secret", "alpha": 12, "coef": "3,2" }

Do not commit watermark.json: it contains the key. Add it to .gitignore.

Limits
------
Survives: H.264/H.265 re-encode at the same resolution, moderate bitrates,
JPEG/PNG round trips, mild denoise.
Does not reliably survive: resizing, cropping, rotating, heavy temporal
denoise, very low bitrates (< ~300 kbps for 1080p), or re-recording a screen.
This is a provenance mark, not DRM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("numpy and pillow are required: python3 -m pip install numpy pillow")

BLOCK = 8
BITS = 128
MARK_BYTES = 12
MAGIC = b"WM"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


# --------------------------------------------------------------------------- #
# Payload
# --------------------------------------------------------------------------- #


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_payload(mark: str) -> bytes:
    raw = mark.encode("utf-8")
    if not raw:
        raise ValueError("mark must not be empty")
    if len(raw) > MARK_BYTES:
        raise ValueError(
            f"mark is {len(raw)} UTF-8 bytes, max {MARK_BYTES}; "
            "use a short ID and keep the full identity in a private registry"
        )
    body = MAGIC + raw.ljust(MARK_BYTES, b"\x00")
    return body + crc16(body).to_bytes(2, "big")


def parse_payload(raw: bytes) -> tuple[str, bool]:
    if len(raw) != BITS // 8:
        return "", False
    body, checksum = raw[:14], int.from_bytes(raw[14:], "big")
    if body[:2] != MAGIC:
        return "", False
    ok = crc16(body) == checksum
    text = body[2:].rstrip(b"\x00").decode("utf-8", "replace")
    return text, ok


def payload_to_bits(payload: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(payload, dtype=np.uint8))


def bits_to_payload(bits: np.ndarray) -> bytes:
    return np.packbits(bits.astype(np.uint8)).tobytes()


# --------------------------------------------------------------------------- #
# 8x8 DCT (orthonormal) without scipy
# --------------------------------------------------------------------------- #


def _dct_matrix(n: int = BLOCK) -> np.ndarray:
    k = np.arange(n).reshape(-1, 1)
    x = np.arange(n).reshape(1, -1)
    d = np.cos(np.pi * (2 * x + 1) * k / (2 * n)) * np.sqrt(2.0 / n)
    d[0] /= np.sqrt(2.0)
    return d.astype(np.float32)


DCT = _dct_matrix()


def to_blocks(y: np.ndarray) -> tuple[np.ndarray, int, int]:
    h8, w8 = y.shape[0] // BLOCK, y.shape[1] // BLOCK
    blocks = (
        y[: h8 * BLOCK, : w8 * BLOCK]
        .reshape(h8, BLOCK, w8, BLOCK)
        .transpose(0, 2, 1, 3)
        .reshape(-1, BLOCK, BLOCK)
        .astype(np.float32)
    )
    return blocks, h8, w8


def from_blocks(coeffs: np.ndarray, y: np.ndarray, h8: int, w8: int) -> np.ndarray:
    pixels = DCT.T @ coeffs @ DCT
    out = y.copy()
    out[: h8 * BLOCK, : w8 * BLOCK] = (
        pixels.reshape(h8, w8, BLOCK, BLOCK)
        .transpose(0, 2, 1, 3)
        .reshape(h8 * BLOCK, w8 * BLOCK)
    )
    return np.clip(out, 0, 255)


def _spread(key: str, nblocks: int) -> tuple[np.ndarray, np.ndarray]:
    seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    pn = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), size=nblocks)
    assign = rng.permutation(nblocks) % BITS
    return pn, assign


def embed_y(
    y: np.ndarray,
    bits: np.ndarray,
    key: str,
    alpha: float,
    coef: tuple[int, int],
) -> np.ndarray:
    blocks, h8, w8 = to_blocks(y)
    coeffs = DCT @ blocks @ DCT.T
    pn, assign = _spread(key, len(blocks))
    signs = np.where(bits[assign], 1.0, -1.0).astype(np.float32)
    u, v = coef
    coeffs[:, u, v] += alpha * pn * signs
    return from_blocks(coeffs, y, h8, w8)


def extract_corr(y: np.ndarray, key: str, coef: tuple[int, int]) -> np.ndarray:
    blocks, _, _ = to_blocks(y)
    coeffs = DCT @ blocks @ DCT.T
    pn, assign = _spread(key, len(blocks))
    u, v = coef
    corr = np.bincount(assign, weights=coeffs[:, u, v] * pn, minlength=BITS)
    counts = np.bincount(assign, minlength=BITS)
    return corr / np.maximum(counts, 1)


# --------------------------------------------------------------------------- #
# Image I/O
# --------------------------------------------------------------------------- #


def image_to_y(path: Path) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(img.convert("YCbCr"), dtype=np.uint8)[..., 0].astype(np.float32)


def embed_image_file(
    path: Path,
    bits: np.ndarray,
    key: str,
    alpha: float,
    coef: tuple[int, int],
    quality: int,
) -> None:
    with Image.open(path) as img:
        ycbcr = np.asarray(img.convert("YCbCr"), dtype=np.uint8).copy()
    ycbcr[..., 0] = embed_y(ycbcr[..., 0].astype(np.float32), bits, key, alpha, coef).astype(
        np.uint8
    )
    out = Image.fromarray(ycbcr, "YCbCr").convert("RGB")
    tmp = path.with_name(path.name + ".wm-tmp")
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        out.save(tmp, format="JPEG", quality=quality, subsampling=0)
    else:
        out.save(tmp, format="PNG")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Config and CLI helpers
# --------------------------------------------------------------------------- #


def coef_tuple(value: str) -> tuple[int, int]:
    try:
        u, v = (int(x) for x in value.split(","))
    except Exception as exc:
        raise argparse.ArgumentTypeError("coef must look like 3,2") from exc
    if not (0 <= u < BLOCK and 0 <= v < BLOCK) or (u == 0 and v == 0):
        raise argparse.ArgumentTypeError("coef must be two indices in 0..7, not the DC term")
    return u, v


def load_config(path: str | None, require_key: bool) -> dict:
    cfg: dict = {}
    if path and Path(path).exists():
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    elif path:
        raise SystemExit(f"config not found: {path}")
    if require_key and not cfg.get("key"):
        raise SystemExit(
            "watermark.json has no key; pass --key or set key in the config"
        )
    return cfg


def resolve_common(args) -> tuple[str, str, float, tuple[int, int], int]:
    cfg = load_config(args.config, require_key=False)
    mark = args.mark if args.mark is not None else cfg.get("mark")
    key = args.key if args.key is not None else cfg.get("key", "")
    alpha = args.alpha if args.alpha is not None else float(cfg.get("alpha", 12.0))
    raw_coef = cfg.get("coef", "3,2")
    if isinstance(raw_coef, (list, tuple)):
        raw_coef = ",".join(str(x) for x in raw_coef)
    coef = args.coef if args.coef is not None else coef_tuple(str(raw_coef))
    quality = args.quality if args.quality is not None else int(cfg.get("quality", 95))
    if not mark:
        raise SystemExit("no mark: pass --mark or set mark in watermark.json")
    if not key:
        print(
            "WARNING: empty key; anyone with this script can extract the mark",
            file=sys.stderr,
        )
    elif key.startswith("replace-with"):
        print(
            "WARNING: key is still the example placeholder; change it before shipping",
            file=sys.stderr,
        )
    if not 4.0 <= alpha <= 30.0:
        raise SystemExit("alpha must be between 4 and 30; 12 is the tested default")
    return mark, key, alpha, coef, quality


# --------------------------------------------------------------------------- #
# embed-frames
# --------------------------------------------------------------------------- #

_W = {}


def _init_worker(payload: bytes, key: str, alpha: float, coef: tuple[int, int], quality: int) -> None:
    _W.update(
        bits=payload_to_bits(payload),
        key=key,
        alpha=alpha,
        coef=coef,
        quality=quality,
    )


def _watermark_one(path_str: str) -> str:
    path = Path(path_str)
    embed_image_file(path, _W["bits"], _W["key"], _W["alpha"], _W["coef"], _W["quality"])
    return path_str


def cmd_embed_frames(args) -> int:
    mark, key, alpha, coef, quality = resolve_common(args)
    payload = build_payload(mark)
    root = Path(args.frames)
    if not root.is_dir():
        raise SystemExit(f"frames directory not found: {root}")
    files = sorted(p for p in root.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not files:
        raise SystemExit(f"no image frames in {root}")

    state_path = root / ".watermark.json"
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    state = {
        "mark": mark,
        "key_sha256": key_hash,
        "alpha": alpha,
        "coef": list(coef),
        "quality": quality,
        "frames": len(files),
    }
    if state_path.exists() and not args.force:
        old = json.loads(state_path.read_text(encoding="utf-8"))
        same = all(old.get(k) == state[k] for k in ("mark", "key_sha256", "alpha", "coef"))
        if same and old.get("complete"):
            print(f"already watermarked with {mark!r}; nothing to do")
            return 0
        if same and not old.get("complete"):
            raise SystemExit(
                "a previous watermark run did not finish. Re-render frames/ "
                "or pass --force (which may double-embed)."
            )
        raise SystemExit(
            "frames/ already carry a different watermark. Re-render frames/ "
            "or pass --force (which may double-embed)."
        )
    if args.force and state_path.exists():
        print("WARNING: --force re-embeds existing frames; the mark may become visible",
              file=sys.stderr)

    state["complete"] = False
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    workers = args.workers or min(8, os.cpu_count() or 1)
    print(f"embedding {len(files)} frames with mark {mark!r} "
          f"(alpha={alpha}, coef={coef[0]},{coef[1]}, workers={workers})")
    done = 0
    try:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(payload, key, alpha, coef, quality),
        ) as pool:
            futures = [pool.submit(_watermark_one, str(p)) for p in files]
            for fut in as_completed(futures):
                fut.result()
                done += 1
                if done % 200 == 0 or done == len(files):
                    print(f"  {done}/{len(files)}")
    except Exception:
        # Leave the state file with complete=False. Re-running must not
        # silently double-embed the frames that already finished.
        raise

    state["complete"] = True
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"watermarked {done} frames")
    return 0


# --------------------------------------------------------------------------- #
# embed-video (streaming, no temp frame dump)
# --------------------------------------------------------------------------- #


def probe_video(path: str) -> dict:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate:format=duration",
            "-of", "json", path,
        ]
    )
    info = json.loads(out)
    stream = info["streams"][0]
    audio = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", path]
    ).strip()
    try:
        duration = float(info.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "rate": stream["r_frame_rate"],
        "duration": duration,
        "audio": bool(audio),
    }


def cmd_embed_video(args) -> int:
    mark, key, alpha, coef, _ = resolve_common(args)
    payload = build_payload(mark)
    bits = payload_to_bits(payload)
    info = probe_video(args.video)
    w, h, rate = info["width"], info["height"], info["rate"]
    if w % BLOCK or h % BLOCK:
        raise SystemExit(f"video size {w}x{h} is not divisible by {BLOCK}")
    total = int(info["duration"] * eval_fraction(rate)) if info["duration"] else 0

    decode_cmd = [
        "ffmpeg", "-v", "error", "-i", args.video,
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    encode_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", rate, "-i", "-",
    ]
    if info["audio"]:
        encode_cmd += ["-i", args.video, "-map", "0:v:0", "-map", "1:a?", "-c:a", "copy",
                       "-map_metadata", "1", "-shortest"]
    encode_cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.out,
    ]

    print(f"embedding mark {mark!r} into {args.video} -> {args.out} ({w}x{h} @ {rate})")
    decoder = subprocess.Popen(decode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    encoder = subprocess.Popen(encode_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_bytes = w * h * 3
    n = 0
    assert decoder.stdout is not None and encoder.stdin is not None
    try:
        while True:
            buf = decoder.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            rgb = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
            ycbcr = np.asarray(Image.fromarray(rgb).convert("YCbCr"), dtype=np.uint8).copy()
            ycbcr[..., 0] = embed_y(
                ycbcr[..., 0].astype(np.float32), bits, key, alpha, coef
            ).astype(np.uint8)
            out_rgb = np.asarray(Image.fromarray(ycbcr, "YCbCr").convert("RGB"))
            encoder.stdin.write(out_rgb.tobytes())
            n += 1
            if n % 200 == 0:
                print(f"  {n}" + (f"/{total}" if total else ""))
    finally:
        if encoder.stdin:
            encoder.stdin.close()
        dec_err = decoder.stderr.read().decode("utf-8", "replace") if decoder.stderr else ""
        enc_err = encoder.stderr.read().decode("utf-8", "replace") if encoder.stderr else ""
        rc_dec = decoder.wait()
        rc_enc = encoder.wait()
    if rc_dec or rc_enc:
        print(dec_err + enc_err, file=sys.stderr)
        raise SystemExit(f"ffmpeg failed (decode={rc_dec}, encode={rc_enc})")
    print(f"watermarked {n} frames -> {args.out}")
    return 0


def eval_fraction(text: str) -> float:
    if "/" in text:
        a, b = text.split("/", 1)
        return float(a) / float(b or 1)
    return float(text)


# --------------------------------------------------------------------------- #
# extract
# --------------------------------------------------------------------------- #


def collect_images(args) -> tuple[list[Path], str | None]:
    if args.image:
        return [Path(args.image)], None
    if args.frames:
        files = sorted(
            p for p in Path(args.frames).iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
        )
        return files, None
    if args.video:
        tmp = tempfile.mkdtemp(prefix="wm-extract-")
        fps = args.fps
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", args.video,
                "-vf", f"fps={fps}", "-frames:v", str(args.max_frames),
                os.path.join(tmp, "f%05d.png"),
            ],
            check=True,
        )
        return sorted(Path(tmp).iterdir()), tmp
    raise SystemExit("pass --video, --image or --frames")


def cmd_extract(args) -> int:
    key = args.key if args.key is not None else ""
    coef = args.coef or coef_tuple("3,2")
    if args.config:
        cfg = load_config(args.config, require_key=not bool(key))
        if not key:
            key = cfg.get("key", "")
        if args.coef is None:
            raw_coef = cfg.get("coef", "3,2")
            if isinstance(raw_coef, (list, tuple)):
                raw_coef = ",".join(str(x) for x in raw_coef)
            coef = coef_tuple(str(raw_coef))
    files, tmp_root = collect_images(args)
    try:
        if not files:
            raise SystemExit("no frames to inspect")
        if len(files) > args.max_frames:
            step = len(files) / args.max_frames
            files = [files[int(i * step)] for i in range(args.max_frames)]

        total_corr = np.zeros(BITS)
        per_frame = 0
        valid_texts: Counter[str] = Counter()
        for path in files:
            corr = extract_corr(image_to_y(path), key, coef)
            total_corr += corr
            text, ok = parse_payload(bits_to_payload(corr > 0))
            if ok:
                valid_texts[text] += 1
            per_frame += 1

        voted = total_corr > 0
        text, crc_ok = parse_payload(bits_to_payload(voted))
        source = "vote"
        if not crc_ok and valid_texts:
            text = valid_texts.most_common(1)[0][0]
            crc_ok = True
            source = "per-frame"
        margin = float(np.mean(np.abs(total_corr / max(per_frame, 1))))
        result = {
            "found": bool(crc_ok),
            "mark": text,
            "crc_ok": bool(crc_ok),
            "frames": per_frame,
            "frames_valid": int(sum(valid_texts.values())),
            "confidence": round(margin, 3),
            "source": source,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if crc_ok else 1
    finally:
        if tmp_root:
            shutil.rmtree(tmp_root, ignore_errors=True)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="watermark.json (mark/key/alpha/coef)")
    p.add_argument("--mark", help="personal mark, max 12 UTF-8 bytes")
    p.add_argument("--key", help="secret key; same key is required to extract")
    p.add_argument("--alpha", type=float, help="embedding strength (default 12)")
    p.add_argument("--coef", type=coef_tuple, help="DCT coefficient u,v (default 3,2)")
    p.add_argument("--quality", type=int, help="JPEG quality when rewriting frames (default 95)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("embed-frames", help="embed into a directory of rendered frames")
    pf.add_argument("--frames", default="frames")
    pf.add_argument("--workers", type=int, default=0)
    pf.add_argument("--force", action="store_true")
    add_common(pf)
    pf.set_defaults(func=cmd_embed_frames)

    pv = sub.add_parser("embed-video", help="embed into an existing MP4 (re-encodes video)")
    pv.add_argument("--video", required=True)
    pv.add_argument("--out", required=True)
    add_common(pv)
    pv.set_defaults(func=cmd_embed_video)

    px = sub.add_parser("extract", help="read the mark from a video, image or frame dir")
    px.add_argument("--video")
    px.add_argument("--image")
    px.add_argument("--frames")
    px.add_argument("--config", help="watermark.json; supplies key/coef")
    px.add_argument("--key", default="")
    px.add_argument("--coef", type=coef_tuple)
    px.add_argument("--fps", type=float, default=2.0)
    px.add_argument("--max-frames", type=int, default=600)
    px.set_defaults(func=cmd_extract)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
