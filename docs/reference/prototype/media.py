"""Tiện ích ffmpeg/ffprobe dùng chung."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], quiet: bool = True, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    if cmd[0] == "ffmpeg" and quiet:
        cmd[1:1] = ["-hide_banner", "-loglevel", "error", "-y"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"Lệnh lỗi: {' '.join(cmd)[:600]}\n{r.stderr[-2500:]}")
    return r


def probe(path: str | Path) -> dict:
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", path])
    d = json.loads(r.stdout)
    v = next((s for s in d.get("streams", []) if s["codec_type"] == "video"), {})
    return {
        "duration": float(d.get("format", {}).get("duration", 0) or 0),
        "width": v.get("width"), "height": v.get("height"),
        "has_audio": any(s["codec_type"] == "audio" for s in d.get("streams", [])),
    }


def last_frame(video: str | Path, out: str | Path) -> Path:
    """Trích khung CUỐI của clip -> làm khung ĐẦU cho clip kế tiếp (giữ chiêu thức liên tục)."""
    out = Path(out)
    run(["ffmpeg", "-sseof", "-0.08", "-i", video, "-update", "1", "-q:v", "1", "-frames:v", "1", out])
    if not out.exists():  # clip quá ngắn
        run(["ffmpeg", "-i", video, "-vf", "reverse", "-frames:v", "1", out])
    return out


def first_frame(video: str | Path, out: str | Path) -> Path:
    run(["ffmpeg", "-i", video, "-frames:v", "1", "-q:v", "1", out])
    return Path(out)


def have(binary: str) -> bool:
    return shutil.which(binary) is not None
