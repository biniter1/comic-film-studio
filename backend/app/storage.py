import re
from pathlib import Path

from app.config import settings
from app.errors import AppError


def resolve_safe_path(base_dir: Path, relative_path: str | Path) -> Path:
    """Safely resolve a relative path inside base_dir, preventing path traversal."""
    path_str = str(relative_path).strip()

    # Reject Windows drive letters (e.g. C:, D:) and absolute paths
    if re.match(r"^[a-zA-Z]:", path_str) or path_str.startswith(("\\\\", "//")):
        raise AppError(
            code="PATH_TRAVERSAL",
            message_vi="Đường dẫn không hợp lệ (không cho phép đường dẫn tuyệt đối hoặc ổ đĩa)",
            details={"path": path_str},
            status_code=400,
        )

    p = Path(path_str)
    if p.is_absolute():
        raise AppError(
            code="PATH_TRAVERSAL",
            message_vi="Đường dẫn không hợp lệ (không cho phép đường dẫn tuyệt đối)",
            details={"path": path_str},
            status_code=400,
        )

    base_resolved = base_dir.resolve()
    target_resolved = (base_resolved / p).resolve()

    try:
        target_resolved.relative_to(base_resolved)
    except ValueError:
        raise AppError(
            code="PATH_TRAVERSAL",
            message_vi="Đường dẫn vượt ra ngoài thư mục dữ liệu cho phép",
            details={"path": path_str},
            status_code=400,
        )

    return target_resolved


def get_data_dir() -> Path:
    return settings.data_dir


def ensure_data_dirs(data_dir: Path | None = None) -> None:
    d = data_dir or get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "logs").mkdir(parents=True, exist_ok=True)
    (d / "jobs").mkdir(parents=True, exist_ok=True)
    (d / "projects").mkdir(parents=True, exist_ok=True)
    (d / "tmp").mkdir(parents=True, exist_ok=True)


def create_project_dir(project_id: str, data_dir: Path | None = None) -> Path:
    d = data_dir or get_data_dir()
    project_dir = resolve_safe_path(d / "projects", project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "refs").mkdir(parents=True, exist_ok=True)
    (project_dir / "chapters").mkdir(parents=True, exist_ok=True)
    return project_dir


def create_chapter_dir(project_id: str, chapter_id: str, data_dir: Path | None = None) -> Path:
    proj_dir = create_project_dir(project_id, data_dir)
    chapter_dir = resolve_safe_path(proj_dir / "chapters", chapter_id)
    chapter_dir.mkdir(parents=True, exist_ok=True)
    for sub in ["pages", "frames", "analysis", "keyframes", "boundary", "takes", "tts", "exports"]:
        (chapter_dir / sub).mkdir(parents=True, exist_ok=True)
    return chapter_dir
