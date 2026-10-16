import pytest

from app.analysis.glossary import apply_glossary
from app.analysis.schemas import DialogueOut
from app.analysis.stages import dialogue_validator, needs_review_for
from app.models.analysis import GlossaryTerm


def term(t, variants, status="approved"):
    return GlossaryTerm(project_id="P", term=t, variants=variants, status=status)


def test_variant_replaced_with_canonical_term():
    terms = [term("Lâm Phong", ["Lam Phong", "Lâm phong"])]
    assert apply_glossary("Lam Phong! lâm phong đâu?", terms) == "Lâm Phong! Lâm Phong đâu?"


def test_word_boundary_not_inside_other_words():
    terms = [term("Linh", ["linh"])]
    assert apply_glossary("Linhh và Tuyết Linh", terms) == "Linhh và Tuyết Linh"
    assert apply_glossary("linh khí", [term("Linh Khí", ["linh khí"])]) == "Linh Khí"


def test_longest_variant_wins_and_flexible_spaces():
    terms = [
        term("Linh Thạch", ["linh thach"]),
        term("Khế Nguyên Linh Thạch", ["khe nguyen  linh thach"]),
    ]
    assert (
        apply_glossary("một viên khe nguyen linh thach", terms) == "một viên Khế Nguyên Linh Thạch"
    )


def test_unapproved_terms_ignored():
    assert (
        apply_glossary("Lam Phong", [term("Lâm Phong", ["Lam Phong"], "suggested")]) == "Lam Phong"
    )


def test_validator_missing_extra_duplicate():
    v = dialogue_validator(["a", "b"])
    v(DialogueOut(lines=[{"line_id": "a", "text": "x"}, {"line_id": "b", "text": "y"}]))
    for lines in (
        [{"line_id": "a", "text": "x"}],
        [
            {"line_id": "a", "text": "x"},
            {"line_id": "b", "text": "y"},
            {"line_id": "c", "text": "z"},
        ],
        [
            {"line_id": "a", "text": "x"},
            {"line_id": "a", "text": "x"},
            {"line_id": "b", "text": "y"},
        ],
    ):
        with pytest.raises(ValueError):
            v(DialogueOut(lines=lines))


def test_length_deviation_flags_review():
    assert needs_review_for("Ngươi dám động vào ta sao?", "Ngươi dám?", None)
    assert not needs_review_for("Ngươi dám động vào ta sao?", "Ngươi dám đụng vào ta ư?", None)
    assert not needs_review_for("Hừ!", "Hừ hừ hừ!", None)  # very short lines exempt
    assert needs_review_for("Đi thôi", "Đi thôi", "đổi nghĩa")  # model left a note
