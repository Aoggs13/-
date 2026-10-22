"""Video enhancement: AI super-resolution on every frame + the photo 'look', then motion-compensated
interpolation to 120 fps. Everything runs on CPU, so the work is shaped to stay tractable:

  1. frames are decoded at a small 'work' size (the x4 model rebuilds edges best from the true-detail size),
     upscaled with the fast SPAN model, graded, resized to the output size and stored as an all-intra
     intermediate at the source frame rate (capped at 30 fps);
  2. ffmpeg's minterpolate is single-threaded, so the intermediate is cut into one time slice per core and
     the slices are interpolated to 120 fps in parallel, then joined;
  3. the result is encoded with x264 at a bitrate that keeps the file under Telegram's upload limit, and the
     original audio is copied back in."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import photo

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
VIDEO_LOOK = photo.Look(detail=0.8, clarity=0.12, vibrance=0.5, saturation=0.15, contrast=0.16)


@dataclass
class Probe:
    width: int
    height: int
    fps: float
    duration: float
    frames: int
    has_audio: bool


def probe(path: str | Path) -> Probe:
    out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                          str(path)], capture_output=True, text=True, check=True, timeout=60,
                         env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")}).stdout
    info = json.loads(out)
    v = next(s for s in info["streams"] if s.get("codec_type") == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", rot) or 0)
    rot = int(v.get("tags", {}).get("rotate", rot) or 0)
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    if not 1 <= fps <= 240:
        fps = 30.0
    dur = float(info.get("format", {}).get("duration") or v.get("duration") or 0)
    frames = int(v.get("nb_frames") or round(dur * fps))
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    return Probe(w, h, fps, dur, frames, has_audio)


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def plan(p: Probe, out_short: int = 1080) -> tuple[tuple[int, int], tuple[int, int]]:
    """(work_w, work_h), (out_w, out_h): x4 from the work size lands at or above the output size."""
    short, long_ = min(p.width, p.height), max(p.width, p.height)
    out_short = min(out_short, max(short * 4, short))
    s = out_short / short
    out = (_even(p.width * s), _even(p.height * s))
    ws = min(1.0, (out_short / 4 * 1.33) / short)              # x4 overshoots a little, then area-down = crisper
    work = (_even(p.width * ws), _even(p.height * ws))
    return work, out


_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}     # children never see the bot token


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, env=_ENV)
    if r.returncode:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")


def enhance_video(src: str | Path, dst: str | Path, out_short: int = 1080, fps_out: int = 120,
                  max_bytes: int = 48 * 1024 * 1024, use_ai: bool = True, workers: int | None = None,
                  progress: Callable[[str, float], None] | None = None, max_seconds: float = 15.0,
                  stop: threading.Event | None = None) -> Probe:
    p = probe(src)
    say = progress or (lambda stage, frac: None)
    work, out = plan(p, out_short)
    fps_in = min(p.fps, 30.0)
    tmp = Path(tempfile.mkdtemp(prefix="enh_"))
    try:
        inter = tmp / "inter.mkv"
        # ---------------------------------------------------------------- 1. per-frame AI upscale + look
        dec = subprocess.Popen([FFMPEG, "-v", "error", "-t", f"{max_seconds:.3f}", "-i", str(src), "-an", "-vf",
                                f"fps={fps_in},scale={work[0]}:{work[1]}:flags=area", "-f", "rawvideo",
                                "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, env=_ENV)
        enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
                                f"{out[0]}x{out[1]}", "-r", f"{fps_in}", "-i", "-", "-c:v", "libx264", "-preset",
                                "ultrafast", "-crf", "10", "-g", "1", "-pix_fmt", "yuv420p", str(inter)],
                               stdin=subprocess.PIPE, env=_ENV)
        max_frames = int(max_seconds * fps_in) + 1                 # metadata can lie: the decoder is capped too
        n_exp = max(1, int(min(p.duration or max_seconds, max_seconds) * fps_in))
        fsize = work[0] * work[1] * 3
        i = 0
        while i < max_frames:
            if stop is not None and stop.is_set():
                dec.kill()
                enc.kill()
                raise RuntimeError("cancelled")
            buf = dec.stdout.read(fsize)
            if len(buf) < fsize:
                break
            fr = np.frombuffer(buf, np.uint8).reshape(work[1], work[0], 3)
            if use_ai:
                up = photo.upscale(fr, "clear_reality_x4", tile=256, pad=10)
                up = cv2.resize(up, out, interpolation=cv2.INTER_AREA if up.shape[1] > out[0] else cv2.INTER_CUBIC)
            else:
                up = cv2.resize(fr, out, interpolation=cv2.INTER_LANCZOS4)
            up = photo.grade(up, VIDEO_LOOK)
            enc.stdin.write(up.tobytes())
            i += 1
            if i % 5 == 0:
                say("upscale", min(0.99, i / n_exp))
        dec.kill()
        dec.wait()
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError("intermediate encode failed")
        if i == 0:
            raise RuntimeError("no frames decoded")
        dur = i / fps_in
        # ---------------------------------------------------------------- 2. 120 fps in parallel time slices
        say("interpolate", 0.0)
        k = max(1, min(workers or os.cpu_count() or 2, int(dur // 0.5) or 1))
        edges = [dur * j / k for j in range(k + 1)]
        mi = (f"minterpolate=fps={fps_out}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1:scd=fdiff")
        parts = [tmp / f"part{j:02d}.mkv" for j in range(k)]
        done = [0]

        def slice_(j: int) -> None:
            # each slice reads one source frame beyond both cuts (the intermediate is all-intra, so seeks are
            # exact) and keeps exactly [t0, t1): the in-between frames across every cut are generated once
            t0, t1 = edges[j], edges[j + 1]
            pre = min(t0, 2.0 / fps_in)
            post = 0.0 if j == k - 1 else 2.0 / fps_in
            if stop is not None and stop.is_set():
                raise RuntimeError("cancelled")
            _run([FFMPEG, "-v", "error", "-y", "-ss", f"{t0 - pre:.6f}", "-to", f"{t1 + post:.6f}", "-i",
                  str(inter), "-vf", f"{mi},trim=start={pre:.6f}:end={pre + (t1 - t0):.6f},setpts=PTS-STARTPTS",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", str(parts[j])])
            done[0] += 1
            say("interpolate", done[0] / k)

        with ThreadPoolExecutor(k) as ex:
            list(ex.map(slice_, range(k)))
        lst = tmp / "parts.txt"
        lst.write_text("".join(f"file '{q}'\n" for q in parts))
        joined = tmp / "joined.mkv"
        _run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
        # ---------------------------------------------------------------- 3. final encode under the size cap
        say("encode", 0.0)
        audio_kbps = 160 if p.has_audio else 0
        vk = int(max_bytes * 8 / max(dur, 0.5) / 1000 * 0.92) - audio_kbps
        vk = max(1500, min(vk, 30000))
        cmd = [FFMPEG, "-v", "error", "-y", "-i", str(joined), "-i", str(src), "-map", "0:v:0"]
        if p.has_audio:
            cmd += ["-map", "1:a:0?", "-c:a", "aac", "-b:a", f"{audio_kbps}k"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-b:v", f"{vk}k", "-maxrate", f"{int(vk * 1.25)}k", "-bufsize", f"{int(vk * 2)}k",
                "-r", str(fps_out), "-movflags", "+faststart", "-shortest", str(dst)]
        _run(cmd)
        say("done", 1.0)
        return probe(dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def eta_seconds(p: Probe, out_short: int = 1080, use_ai: bool = True) -> int:
    """Rough CPU estimate (calibrated on a 4-core box; scales with cores)."""
    work, out = plan(p, out_short)
    frames = p.duration * min(p.fps, 30.0)
    cores = os.cpu_count() or 2
    sr = frames * (work[0] * work[1] / 0.23e6) * 1.25 * (4 / cores) if use_ai else frames * 0.2
    mi = p.duration * 29 * (out[0] * out[1] / (1080 * 1920)) * (4 / cores)
    return int(sr + mi + 15)


def frame_at(path: str | Path, t: float) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, fr = cap.read()
    cap.release()
    return fr if ok else None
