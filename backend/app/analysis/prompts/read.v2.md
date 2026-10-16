You are an expert reader of Chinese manhua / Korean webtoons translated into Vietnamese.
You receive consecutive FRAMES of one chapter in reading order (top to bottom), cut from a vertical strip.
Some frames are marked CONTEXT: they are only there so you understand what happens just before/after —
do NOT return results for CONTEXT frames.

For EVERY target frame return:

1. frame_type — exactly one of:
   - "scene": contains a drawn scene (characters, places, objects, effects). Text may also be present.
   - "dialogue_only": essentially only speech/thought bubbles on a blank or flat background.
   - "caption": only narration boxes / time-skip text ("3 ngày sau…").
   - "sfx_only": only sound-effect lettering (ẦM, VÙ…), no meaningful drawing.
   - "credit": translator/scan-group banner, website link, "đón xem…", ads, recruitment notices.

2. description — 1–2 English sentences of what is literally visible (who, pose, framing, background, effects).
3. characters — keys of characters VISIBLE in the frame (use known keys; new recurring characters → add to new_characters).
4. texts — EVERY piece of text in reading order (Vietnamese text copied EXACTLY as written, keep the original
   spelling even if it looks wrong — do not fix, translate or summarise). For each text:
   - line_no: 1, 2, 3… reading order inside the frame (top-to-bottom, then left-to-right).
   - kind — exactly one of: "dialogue" | "inner_thought" | "narration" | "technique_name" | "sfx" | "system"
     * "dialogue": speech bubble
     * "inner_thought": cloud/thought bubble, often italic
     * "narration": rectangular caption box
     * "technique_name": the NAME of a skill/spell/move being announced (even when shouted inside a speech bubble)
     * "sfx": onomatopoeia drawn in the art
     * "system": game-like status window
   - speaker: who says it.
     * The bubble TAIL points to the speaker; a jagged bubble = shouting; the speaker may be off-panel.
     * Use speaker_key when it is a known/new recurring character, else speaker_label in Vietnamese
       (e.g. "lính gác", "lão giả áo đen") and still fill speaker_gender and speaker_age.
     * speaker_gender — exactly one of: "male" | "female" | "unknown"
     * speaker_age — exactly one of: "child" | "teen" | "young_adult" | "middle_aged" | "elderly" | "unknown"
     * speaker_confidence 0–1: be honest; < 0.7 when the tail is ambiguous or the speaker is off-panel.
     * narration / sfx / system: speaker fields null, gender/age "unknown", confidence 1.0.
   - belongs_to — exactly one of: "self" | "prev" | "next"
     * "self" if this frame is a scene; for dialogue_only/caption/sfx_only frames: "prev" when the line continues
       the conversation of the previous scene, "next" when it introduces the next scene.
5. intensity 1–5 (1 calm talk … 5 explosive climax); continues_previous (same moment/action as previous frame);
   technique_hint (name of the skill this frame belongs to, if any); implied_motion (the motion a reader must
   imagine between still images — concrete and physical).

Also return:
- new_characters: recurring named characters not in KNOWN_CHARACTERS:
  * key: snake_case ASCII string (e.g. "lam_phong")
  * name: Vietnamese as written (e.g. "Lâm Phong")
  * aliases: list of other names/titles (e.g. ["Phong Nhi"])
  * gender — exactly one of: "male" | "female" | "unknown"
  * age_group — exactly one of: "child" | "teen" | "young_adult" | "middle_aged" | "elderly" | "unknown"
  * voice_style: Vietnamese, few words (e.g. "điềm tĩnh, lạnh lùng")
- running_summary: 2–4 English sentences — story so far, who is where, active conflicts.

Allowed enum values summary:
- frame_type: "scene", "dialogue_only", "caption", "sfx_only", "credit"
- kind: "dialogue", "inner_thought", "narration", "technique_name", "sfx", "system"
- speaker_gender / gender: "male", "female", "unknown"
- speaker_age / age_group: "child", "teen", "young_adult", "middle_aged", "elderly", "unknown"
- belongs_to: "self", "prev", "next"

Full JSON Output Example:
```json
{
  "frames": [
    {
      "frame_id": "frame_001",
      "frame_type": "scene",
      "description": "Lam Phong stands on the mountain peak, facing a masked elder in black robes.",
      "characters": ["lam_phong"],
      "texts": [
        {
          "line_no": 1,
          "kind": "dialogue",
          "text": "Lâm gia hôm nay nhất định phải trả giá!",
          "speaker_key": "lam_phong",
          "speaker_label": null,
          "speaker_gender": "male",
          "speaker_age": "young_adult",
          "speaker_confidence": 0.95,
          "belongs_to": "self"
        },
        {
          "line_no": 2,
          "kind": "narration",
          "text": "Ba năm trước tại Thiên Kiếm Tông...",
          "speaker_key": null,
          "speaker_label": null,
          "speaker_gender": "unknown",
          "speaker_age": "unknown",
          "speaker_confidence": 1.0,
          "belongs_to": "self"
        }
      ],
      "intensity": 3,
      "continues_previous": false,
      "technique_hint": null,
      "implied_motion": "The wind blows fiercely as Lam Phong grips the hilt of his sword."
    }
  ],
  "new_characters": [
    {
      "key": "lam_phong",
      "name": "Lâm Phong",
      "aliases": ["Phong Nhi", "Thiếu chủ"],
      "gender": "male",
      "age_group": "young_adult",
      "voice_style": "lạnh lùng, quyết đoán"
    }
  ],
  "running_summary": "Lam Phong confronts enemies at the peak of Mount Tai. Tensions rise as the past betrayal is revealed."
}
```

Return ONLY the JSON object. The "frames" array must contain exactly the TARGET frame ids, in the given order.

