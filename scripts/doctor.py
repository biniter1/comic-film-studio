"""scripts/doctor.py — Kiểm tra môi trường cho Comic Film Studio trên Windows 11.

Chạy: python scripts/doctor.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class Check:
    name: str
    ok: bool
    version: Optional[str]
    install_hint: Optional[str]


def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        out = (res.stdout + res.stderr).strip().splitlines()
        return res.returncode == 0, out[0] if out else ""
    except Exception as e:
        return False, str(e)


def check_python312() -> Check:
    ok, ver = _run([sys.executable, "--version"])
    is_312 = ok and "3.12" in ver
    hint = None if is_312 else "winget install astral-sh.uv  # rồi: uv python install 3.12"
    return Check("Python 3.12", is_312, ver if ok else None, hint)


def check_uv() -> Check:
    exe = shutil.which("uv")
    if exe:
        ok, ver = _run(["uv", "--version"])
        return Check("uv (package manager)", ok, ver if ok else None, None)
    # Try via python -m uv
    ok, ver = _run([sys.executable, "-m", "uv", "--version"])
    if ok:
        return Check("uv (package manager)", True, ver, None)
    hint = (
        "powershell -ExecutionPolicy ByPass -c "
        '"irm https://astral.sh/uv/install.ps1 | iex"'
        "\nHoặc: python -m pip install uv"
    )
    return Check("uv (package manager)", False, None, hint)


def check_node() -> Check:
    ok, ver = _run(["node", "--version"])
    if ok:
        try:
            major = int(ver.lstrip("v").split(".")[0])
            is_lts = major >= 18
        except Exception:
            is_lts = False
        hint = None if is_lts else "winget install OpenJS.NodeJS.LTS"
        return Check("Node.js (>= 18 LTS)", is_lts, ver, hint)
    return Check("Node.js (>= 18 LTS)", False, None, "winget install OpenJS.NodeJS.LTS")


def check_npm() -> Check:
    ok, ver = _run(["npm", "--version"])
    return Check("npm", ok, ver if ok else None, "Cài cùng với Node.js" if not ok else None)


def check_ffmpeg() -> Check:
    ok, ver = _run(["ffmpeg", "-version"])
    if ok:
        first_line = ver.splitlines()[0] if "\n" in ver else ver
        return Check("ffmpeg", True, first_line[:80], None)
    hint = (
        "winget install Gyan.FFmpeg\n"
        "Sau đó mở terminal mới và chạy: ffmpeg -version\n"
        "(Lưu ý: Phase 0/1 không cần ffmpeg. Cần từ Phase 3 trở đi.)"
    )
    return Check("ffmpeg", False, None, hint)


def check_git() -> Check:
    ok, ver = _run(["git", "--version"])
    return Check("git", ok, ver if ok else None, "winget install Git.Git" if not ok else None)


def main() -> None:
    print("=" * 60)
    print("  Comic Film Studio — Kiểm tra môi trường (doctor)")
    print("=" * 60)
    print()

    checks = [
        check_python312(),
        check_uv(),
        check_node(),
        check_npm(),
        check_ffmpeg(),
        check_git(),
    ]

    all_critical_ok = True
    critical_names = {"Python 3.12", "uv (package manager)", "Node.js (>= 18 LTS)", "npm", "git"}

    for c in checks:
        icon = "✅" if c.ok else "❌"
        label = f"{icon} {c.name}"
        ver_str = f"  ({c.version})" if c.version else ""
        print(f"  {label}{ver_str}")
        if not c.ok and c.install_hint:
            for line in c.install_hint.splitlines():
                print(f"       → {line}")
        if not c.ok and c.name in critical_names:
            all_critical_ok = False

    print()
    if all_critical_ok:
        print("✅ Môi trường sẵn sàng. Bạn có thể chạy: cd backend && uv run cfs")
    else:
        print("❌ Có công cụ bắt buộc chưa cài. Vui lòng cài đặt theo hướng dẫn ở trên.")
        print("   Sau đó mở terminal mới và chạy lại: python scripts/doctor.py")
    print()


if __name__ == "__main__":
    main()

