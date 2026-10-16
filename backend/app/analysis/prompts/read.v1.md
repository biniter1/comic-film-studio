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
   - kind: dialogue (speech bubble) | inner_thought (cloud/thought bubble, often italic) | narration (rectangular
     caption box) | technique_name (the NAME of a skill/spell/move being announced — even when shouted inside a
     speech bubble) | sfx (onomatopoeia drawn in the art) | system (game-like status window).
   - speaker: who says it.
       * The bubble TAIL points to the speaker; a jagged bubble = shouting; the speaker may be off-panel.
       * Use speaker_key when it is a known/new recurring character, else speaker_label in Vietnamese
         (e.g. "lính gác", "lão giả áo đen") and still fill speaker_gender and speaker_age.
       * speaker_confidence 0–1: be honest; < 0.7 when the tail is ambiguous or the speaker is off-panel.
       * narration / sfx / system: speaker fields null, gender/age "unknown", confidence 1.
   - belongs_to: which SCENE the line should be shown with when animated:
       "self" if this frame is a scene; for dialogue_only/caption/sfx_only frames: "prev" when the line continues
       the conversation of the previous scene, "next" when it introduces the next scene.
5. intensity 1–5 (1 calm talk … 5 explosive climax); continues_previous (same moment/action as previous frame);
   technique_hint (name of the skill this frame belongs to, if any); implied_motion (the motion a reader must
   imagine between still images — concrete and physical).

Also return:
- new_characters: recurring named characters not in KNOWN_CHARACTERS: key (snake_case ASCII), name (Vietnamese as
  written), aliases, gender, age_group, voice_style (Vietnamese, few words, e.g. "điềm tĩnh, lạnh lùng").
- running_summary: 2–4 English sentences — story so far, who is where, active conflicts.

Return ONLY JSON:
{"frames": [{"frame_id", "frame_type", "description", "characters", "texts": [...], "intensity",
"continues_previous", "technique_hint", "implied_motion"}], "new_characters": [...], "running_summary": "..."}
The "frames" array must contain exactly the TARGET frame ids, in the given order.
