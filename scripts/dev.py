import signal
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    backend_dir = root_dir / "backend"
    frontend_dir = root_dir / "frontend"

    print("=== Khởi động Comic Film Studio (Chế độ phát triển) ===")
    print(f"Backend:  http://127.0.0.1:8765")
    print(f"Frontend: http://localhost:5173")
    print("Nhấn Ctrl+C để dừng toàn bộ tiến trình.\n")

    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    backend_proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765", "--reload"],
        cwd=str(backend_dir),
    )

    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(frontend_dir),
    )

    def cleanup(signum=None, frame=None) -> None:
        print("\nĐang dừng các tiến trình...")
        for p in (backend_proc, frontend_proc):
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        print("Đã đóng tất cả tiến trình.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        while True:
            if backend_proc.poll() is not None:
                print("Backend đã dừng.")
                cleanup()
            if frontend_proc.poll() is not None:
                print("Frontend đã dừng.")
                cleanup()
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
