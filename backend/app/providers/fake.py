"""Deterministic provider for tests: responses come from a callable or a queue per stage."""

from collections.abc import Callable

from app.providers.base import ProviderRequest


class FakeProvider:
    name = "fake"

    def __init__(self, respond: Callable[[ProviderRequest], str]):
        self.respond = respond
        self.calls: list[ProviderRequest] = []

    def generate(self, req: ProviderRequest) -> str:
        self.calls.append(req)
        return self.respond(req)


def e2e_responder(req: ProviderRequest) -> str:
    """Scripted answers for the browser E2E test (enabled by CFS_FAKE_PROVIDER=e2e).

    read: the middle TARGET frame is `dialogue_only` (its line belongs to the previous scene),
    every other frame is a scene with one line. dialogue: adds "!" to raw lines ending in ".".
    """
    import json

    if req.stage == "plan":
        data = json.loads(req.user_text)
        ids = [f["frame_id"] for f in data["SCENE_FRAMES"]]
        return json.dumps(
            {
                "scenes": [
                    {
                        "frame_ids": ids,
                        "summary": "e2e scene",
                        "location_key": "dai_dien",
                        "mood": "tense",
                    }
                ],
                "new_locations": [
                    {
                        "key": "dai_dien",
                        "name_vi": "Đại điện",
                        "location_lock": "stone hall with red pillars",
                    }
                ],
            }
        )
    if req.stage == "shots":
        data = json.loads(req.user_text)
        return json.dumps(
            {
                "shots": [
                    {
                        "frame_ids": [f["frame_id"]],
                        "transition_in": "cut",
                        "duration_s": 4,
                        "camera": {"shot_size": "medium", "movement": "push_in", "speed": "slow"},
                        "blocking": [
                            {
                                "character_key": "lam_phong",
                                "screen_pos": "left",
                                "depth": "mg",
                                "facing": "right",
                                "pose": "standing",
                            }
                        ],
                        "beats": [
                            {"t0": 0, "t1": 2, "action": "wind moves his robe"},
                            {"t0": 2, "t1": 4, "action": "he raises his eyes"},
                        ],
                        "start_state": "standing still",
                        "end_state": "looking up",
                        "line_ids": [],
                    }
                    for f in data["FRAMES"]
                ]
            }
        )
    if req.stage == "character_profile":
        return json.dumps(
            {
                "look_lock": "young man, long black hair tied high, sharp red eyes, athletic build",
                "outfit_lock": "black martial arts robe with silver trim, leather belt",
                "short_id": "black martial arts robe",
                "height_class": "average",
                "palette": ["black", "silver", "red"],
                "distinctive": ["sharp red eyes", "high ponytail"],
            },
            ensure_ascii=False,
        )

    data = json.loads(req.user_text)
    if req.stage == "read":
        targets = data["TARGET_FRAMES"]
        mid = len(targets) // 2 if len(targets) >= 3 else -1
        frames = []
        for i, fid in enumerate(targets):
            only = i == mid
            frames.append(
                {
                    "frame_id": fid,
                    "frame_type": "dialogue_only" if only else "scene",
                    "description": "test frame",
                    "characters": ["lam_phong"] if i % 2 == 0 or not only else [],
                    "texts": [
                        {
                            "line_no": 1,
                            "kind": "dialogue",
                            "text": f"Câu thoại khung {i + 1}.",
                            "speaker_key": "lam_phong" if i % 2 == 0 else None,
                            "speaker_label": None if i % 2 == 0 else "lão giả",
                            "speaker_gender": "male",
                            "speaker_age": "young_adult" if i % 2 == 0 else "elderly",
                            "speaker_confidence": 0.95 if i % 2 == 0 else 0.4,
                            "belongs_to": "prev" if only else "self",
                        }
                    ],
                }
            )
        return json.dumps(
            {
                "frames": frames,
                "new_characters": [
                    {
                        "key": "lam_phong",
                        "name": "Lâm Phong",
                        "gender": "male",
                        "age_group": "young_adult",
                    }
                ],
                "running_summary": "e2e",
            },
            ensure_ascii=False,
        )
    lines = [
        {"line_id": x["line_id"], "text": x["text"].rstrip(".") + "!"} for x in data["TARGET_LINES"]
    ]
    return json.dumps(
        {"lines": lines, "glossary_candidates": [{"term": "Lâm Phong", "kind": "person"}]},
        ensure_ascii=False,
    )
