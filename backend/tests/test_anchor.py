from types import SimpleNamespace

from app.analysis.stages import compute_anchor


def fr(*types):
    return [SimpleNamespace(id=f"F{i}", frame_type=t) for i, t in enumerate(types)]


def test_scene_anchors_to_itself():
    assert compute_anchor(fr("scene", "scene"), 1, "prev") == "F1"


def test_dialogue_only_between_scenes_follows_belongs_to():
    f = fr("scene", "dialogue_only", "scene")
    assert compute_anchor(f, 1, "prev") == "F0"
    assert compute_anchor(f, 1, "next") == "F2"


def test_start_and_end_of_chapter_fall_back_to_other_side():
    f = fr("dialogue_only", "scene", "caption")
    assert compute_anchor(f, 0, "prev") == "F1"
    assert compute_anchor(f, 2, "next") == "F1"


def test_several_dialogue_only_in_a_row():
    f = fr("scene", "dialogue_only", "dialogue_only", "sfx_only", "scene")
    assert compute_anchor(f, 2, "prev") == "F0"
    assert compute_anchor(f, 2, "next") == "F4"
    assert compute_anchor(f, 3, "self") == "F0"  # "self" on a non-scene behaves like prev


def test_no_scene_at_all():
    assert compute_anchor(fr("dialogue_only", "credit"), 0, "next") is None


def test_unclassified_frame_counts_as_scene():
    assert compute_anchor(fr(None), 0, "prev") == "F0"
