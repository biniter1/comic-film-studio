from app.analysis import shot_rules as R


def ctx(**kw):
    base = dict(
        frame_scene={"F1": "S1", "F2": "S1", "F3": "S2"},
        frame_asset={"F1": "A1", "F2": "A2", "F3": "A3"},
        frame_chars={"F1": ["hero"], "F2": ["hero", "elder"], "F3": ["elder"]},
        lines={
            "L1": {"kind": "dialogue", "text": "Ngươi là ai?", "anchor_frame_id": "F1", "order": 1},
            "L2": {
                "kind": "technique_name",
                "text": "Huyết Ma Chưởng!",
                "anchor_frame_id": "F2",
                "order": 2,
            },
            "L3": {"kind": "dialogue", "text": "x" * 140, "anchor_frame_id": "F3", "order": 3},
        },
        chars={
            "hero": R.CharInfo(
                "hero",
                "Lâm Phong",
                role="main",
                look_lock="young man, black hair",
                outfits={
                    "default": {
                        "outfit_lock": "black robe",
                        "short_id": "the young man in black",
                        "sheet_asset_id": "SHEET1",
                    }
                },
                default_outfit="default",
            ),
            "elder": R.CharInfo(
                "elder",
                "Đồ Trưởng Lão",
                role="supporting",
                look_lock="old man",
                outfits={
                    "default": {"outfit_lock": "white robe", "short_id": "", "sheet_asset_id": None}
                },
                default_outfit="default",
            ),
            "crowd": R.CharInfo("crowd", "Đệ tử", role="extra", is_group=True),
        },
        locs={"hall": R.LocInfo("hall", "Đại điện", "stone hall, red pillars", "LOCSHEET")},
    )
    base.update(kw)
    return R.Ctx(**base)


def shot(**kw):
    s = {
        "transition_in": "cut",
        "frame_ids": ["F1"],
        "duration_s": 4.0,
        "camera": {"shot_size": "medium", "movement": "push_in", "speed": "slow", "angle": "eye"},
        "blocking": [],
        "beats": [{"t0": 0, "t1": 4, "action": "he looks up"}],
        "start_state": "",
        "end_state": "",
        "action": "",
        "line_ids": [],
    }
    s.update(kw)
    return s


SCENES = [
    {"id": "S1", "frame_ids": ["F1", "F2"], "location_key": "hall"},
    {"id": "S2", "frame_ids": ["F3"], "location_key": None},
]


def test_missing_lines_attached_and_technique_becomes_title():
    c = ctx()
    s1 = [shot(frame_ids=["F1"]), shot(frame_ids=["F2"])]
    s2 = [shot(frame_ids=["F3"])]
    flat = R.apply_rules(SCENES, {"S1": s1, "S2": s2}, c)
    assert flat[0]["line_ids"] == ["L1"] and flat[1]["line_ids"] == ["L2"]
    assert flat[1]["titles"] == [
        {"text": "Huyết Ma Chưởng!", "style": "technique", "line_id": "L2"}
    ]
    assert any("Bổ sung câu bị sót" in n for n in flat[0]["rule_notes"])
    assert [s["code"] for s in flat] == ["SH001", "SH002", "SH003"]


def test_duration_extended_for_reading_and_long_warning():
    flat = R.apply_rules(
        SCENES,
        {"S1": [shot(frame_ids=["F1", "F2"])], "S2": [shot(frame_ids=["F3"], line_ids=["L3"])]},
        ctx(),
    )
    assert flat[1]["duration_s"] >= 10
    assert any("nên tách shot" in n for n in flat[1]["rule_notes"])


def test_continuous_at_scene_start_becomes_cut_and_chains():
    flat = R.apply_rules(
        SCENES,
        {
            "S1": [shot(frame_ids=["F1"]), shot(frame_ids=["F2"], transition_in="continuous")],
            "S2": [shot(frame_ids=["F3"], transition_in="continuous")],
        },
        ctx(),
    )
    assert [(s["chain_code"], s["chain_pos"]) for s in flat] == [("C01", 1), ("C01", 2), ("C02", 1)]
    assert flat[2]["transition_in"] == "cut"


def test_beats_cover_duration():
    sh = shot(
        duration_s=4.0,
        beats=[
            {"t0": 0.5, "t1": 1, "action": "a"},
            {"t0": 2, "t1": 3, "action": "b"},
            {"t0": 3, "t1": 3.5, "action": "c"},
            {"t0": 3.5, "t1": 3.9, "action": "d"},
        ],
    )
    R.fix_beats(sh)
    assert sh["beats"][0]["t0"] == 0 and sh["beats"][-1]["t1"] == 4.0 and len(sh["beats"]) == 3
    assert all(a["t1"] == b["t0"] for a, b in zip(sh["beats"], sh["beats"][1:]))


def test_axis_flip_warning():
    left = {"character_key": "hero", "screen_pos": "left"}
    right = {"character_key": "elder", "screen_pos": "right"}
    a = shot(frame_ids=["F1"], blocking=[dict(left), dict(right)])
    b = shot(
        frame_ids=["F2"], blocking=[dict(left, screen_pos="right"), dict(right, screen_pos="left")]
    )
    flat = R.apply_rules(SCENES, {"S1": [a, b]}, ctx())
    assert any("lật trục" in n for n in flat[1]["rule_notes"])


def test_compose_attachments_and_prompts():
    c = ctx()
    sh = shot(
        frame_ids=["F2"],
        location_key="hall",
        blocking=[
            {
                "character_key": "elder",
                "outfit_key": "default",
                "screen_pos": "right",
                "depth": "mg",
                "facing": "left",
                "pose": "arms crossed",
            },
            {
                "character_key": "hero",
                "outfit_key": "default",
                "screen_pos": "left",
                "depth": "fg",
                "facing": "right",
                "pose": "",
            },
            {
                "character_key": "crowd",
                "screen_pos": "center",
                "depth": "bg",
                "facing": "camera",
                "pose": "",
            },
        ],
        beats=[
            {"t0": 0, "t1": 2, "action": "he raises his palm"},
            {"t0": 2, "t1": 4, "action": "red light bursts out"},
        ],
        start_state="palm raised",
        end_state="red glow fills the frame",
    )
    R.compose(sh, c)
    kinds = [a["kind"] for a in sh["attachments"]]
    assert kinds == ["frame", "char_sheet", "location_sheet"]  # elder has no approved sheet
    kp = sh["keyframe_prompt"]
    assert "Image 2 is the character sheet of Lâm Phong" in kp
    assert "Image 3 is the location sheet of Đại điện" in kp
    assert "In the background: Đệ tử" in kp and "Location: stone hall" in kp
    vp = sh["video_prompt"]
    assert vp.startswith("Push in, slow, medium shot.")
    assert "First, he raises his palm." in vp and "Finally, red light bursts out." in vp
    assert "Ends on: red glow fills the frame." in vp
    assert "the young man in black" in vp and len(vp.split()) <= R.MAX_VIDEO_WORDS


def test_max_ref_images_respected():
    c = ctx(max_ref_images=1)
    sh = shot(
        frame_ids=["F1"],
        location_key="hall",
        blocking=[{"character_key": "hero", "outfit_key": "default"}],
    )
    R.compose(sh, c)
    assert [a["kind"] for a in sh["attachments"]] == ["frame"]
