from pathlib import Path

import pytest

from app.errors import AppError
from app.storage import create_chapter_dir, create_project_dir, resolve_safe_path


def test_resolve_safe_path_valid(tmp_path: Path):
    target = resolve_safe_path(tmp_path, "subfolder/file.txt")
    assert target == (tmp_path / "subfolder" / "file.txt").resolve()


def test_resolve_safe_path_traversal_dot_dot(tmp_path: Path):
    with pytest.raises(AppError) as exc_info:
        resolve_safe_path(tmp_path, "../outside.txt")
    assert exc_info.value.code == "PATH_TRAVERSAL"

    with pytest.raises(AppError) as exc_info:
        resolve_safe_path(tmp_path, "a/../../outside.txt")
    assert exc_info.value.code == "PATH_TRAVERSAL"


def test_resolve_safe_path_absolute(tmp_path: Path):
    with pytest.raises(AppError) as exc_info:
        resolve_safe_path(tmp_path, "/etc/passwd")
    assert exc_info.value.code == "PATH_TRAVERSAL"


def test_resolve_safe_path_windows_drive(tmp_path: Path):
    with pytest.raises(AppError) as exc_info:
        resolve_safe_path(tmp_path, "C:\\Windows\\System32")
    assert exc_info.value.code == "PATH_TRAVERSAL"

    with pytest.raises(AppError) as exc_info:
        resolve_safe_path(tmp_path, "d:/test/file")
    assert exc_info.value.code == "PATH_TRAVERSAL"


def test_resolve_safe_path_unc(tmp_path: Path):
    with pytest.raises(AppError) as exc_info:
        resolve_safe_path(tmp_path, "\\\\server\\share\\file.txt")
    assert exc_info.value.code == "PATH_TRAVERSAL"


def test_create_project_and_chapter_dirs(tmp_path: Path):
    proj_dir = create_project_dir("p1", data_dir=tmp_path)
    assert proj_dir.exists()
    assert (proj_dir / "refs").exists()
    assert (proj_dir / "chapters").exists()

    chap_dir = create_chapter_dir("p1", "c1", data_dir=tmp_path)
    assert chap_dir.exists()
    assert (chap_dir / "pages").exists()
    assert (chap_dir / "frames").exists()
    assert (chap_dir / "analysis").exists()
    assert (chap_dir / "takes").exists()
