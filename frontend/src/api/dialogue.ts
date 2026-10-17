import { Job, request } from "./client";

export type FrameType = "scene" | "dialogue_only" | "caption" | "sfx_only" | "credit";
export type TextKind = "dialogue" | "inner_thought" | "narration" | "technique_name" | "sfx" | "system";
export type Gender = "male" | "female" | "unknown";
export type AgeGroup = "child" | "teen" | "young_adult" | "middle_aged" | "elderly" | "unknown";
export type ReviewStatus = "suggested" | "approved" | "rejected";

export interface SpeakerSuggestion {
  speaker_key?: string | null;
  speaker_label?: string | null;
  reason: string;
}

export interface DialogueLine {
  id: string;
  chapter_id: string;
  order: number;
  source_frame_id: string;
  anchor_frame_id: string | null;
  anchor_locked: boolean;
  belongs_to: "self" | "prev" | "next";
  line_no: number;
  kind: TextKind;
  speaker_key: string | null;
  speaker_label: string | null;
  speaker_gender: Gender;
  speaker_age: AgeGroup;
  speaker_confidence: number;
  text_raw: string;
  text: string;
  edited_by: "none" | "ai" | "user";
  edit_note: string | null;
  needs_review: boolean;
  reviewed: boolean;
  speaker_suggestion?: SpeakerSuggestion | null;
}

export type HeightClass = "child" | "short" | "average" | "tall" | "giant";
export type LookStatus = "draft" | "approved";
export type SheetStatus = "missing" | "pending" | "approved";

export interface CharacterOutfit {
  id: string;
  character_id: string;
  key: string;
  name_vi: string;
  outfit_lock: string | null;
  short_id: string | null;
  is_default: boolean;
  sheet_asset_id: string | null;
  sheet_status: SheetStatus;
  sheet_url: string | null;
  note: string | null;
  created_at?: string;
}

export interface Character {
  id: string;
  project_id: string;
  key: string;
  name: string;
  aliases: string[];
  gender: Gender;
  age_group: AgeGroup;
  voice_style: string | null;
  look_lock: string | null;
  height_class: HeightClass;
  ref_frame_ids: string[];
  look_status: LookStatus;
  status: ReviewStatus;
  line_count?: number;
  outfits?: CharacterOutfit[];
}

export interface LocationItem {
  id: string;
  project_id: string;
  key: string;
  name_vi: string;
  aliases: string[];
  location_lock: string | null;
  ref_frame_ids: string[];
  sheet_asset_id: string | null;
  sheet_status: SheetStatus;
  sheet_url: string | null;
  created_at?: string;
}

export interface BibleData {
  project_id: string;
  characters: Character[];
  locations: LocationItem[];
}

export interface FrameSuggestion {
  id: string;
  chapter_id: string;
  idx: number;
  frame_type: FrameType | null;
  image_url: string;
}

export interface DialogueFrame {
  id: string;
  idx: number;
  frame_type: FrameType | null;
  frame_type_source: "ai" | "user" | null;
  description: string;
  characters?: string[];
  image_url: string;
}

export interface UnitInfo {
  unit_index: number;
  mode: "api" | "manual";
  status: "pending" | "awaiting_paste" | "succeeded" | "failed";
  error: string | null;
  size?: number;
}

export interface ReadProgress {
  succeeded: number;
  total: number;
  unread_frames?: number;
  total_frames?: number;
  remaining_units?: number;
}

export interface DialogueData {
  chapter_id: string;
  project_id: string;
  status: string;
  busy_job_id: string | null;
  read_progress?: ReadProgress;
  frames: DialogueFrame[];
  lines: DialogueLine[];
  characters: Character[];
  stats: { lines: number; pending_review: number; edited_ai: number; edited_user: number };
  units: { read: UnitInfo[]; dialogue: UnitInfo[] };
}

export interface GlossaryTerm {
  id: string;
  term: string;
  kind: string;
  variants: string[];
  note: string | null;
  status: ReviewStatus;
}

export interface AddressRule {
  id: string;
  speaker_key: string;
  listener_key: string;
  self_term: string;
  address_term: string;
  note: string | null;
  status: ReviewStatus;
}

export type Stage = "read" | "dialogue";

export type LinePatch = Partial<
  Pick<DialogueLine, "text" | "speaker_key" | "speaker_label" | "kind" | "reviewed" | "speaker_suggestion">
> & { anchor_frame_id?: string | null };

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export const dialogueApi = {
  get: (cid: string) => request<DialogueData>(`/chapters/${cid}/dialogue`),
  startApi: (cid: string, stage: Stage, options?: { force_all?: boolean; then_dialogue?: boolean }) =>
    request<{ jobs: Job[] }>(`/chapters/${cid}/analysis/${stage}`, {
      method: "POST",
      ...json({
        mode: "api",
        then_dialogue: options?.then_dialogue ?? true,
        force_all: options?.force_all ?? false,
      }),
    }),
  startManual: (cid: string, stage: Stage, options?: { force_all?: boolean }) =>
    request<{ units: UnitInfo[] }>(`/chapters/${cid}/analysis/${stage}`, {
      method: "POST",
      ...json({ mode: "manual", force_all: options?.force_all ?? false }),
    }),
  units: (cid: string, stage: Stage) => request<UnitInfo[]>(`/chapters/${cid}/analysis/${stage}/units`),
  bundleUrl: (cid: string, stage: Stage, unit: number) =>
    `/api/chapters/${cid}/analysis/${stage}/bundle?unit=${unit}`,
  paste: (cid: string, stage: Stage, unit_index: number | null | undefined, raw: string) =>
    request<{ units: UnitInfo[]; matched_unit?: number; message_vi?: string }>(
      `/chapters/${cid}/analysis/${stage}/paste`,
      {
        method: "POST",
        ...json({ unit_index: unit_index ?? undefined, raw }),
      }
    ),

  patchLine: (lid: string, patch: LinePatch) =>
    request<DialogueLine>(`/dialogue/${lid}`, { method: "PATCH", ...json(patch) }),
  applySpeakerSuggestion: (lid: string) =>
    request<DialogueLine>(`/dialogue/${lid}/apply-speaker-suggestion`, { method: "POST" }),
  revertLine: (lid: string) => request<DialogueLine>(`/dialogue/${lid}/revert`, { method: "POST" }),
  reviewAll: (cid: string) =>
    request<{ reviewed: number }>(`/chapters/${cid}/dialogue/review-all`, { method: "POST" }),
  approve: (cid: string) => request<{ status: string }>(`/chapters/${cid}/dialogue/approve`, { method: "POST" }),
  applyGlossary: (cid: string) =>
    request<{ changed: number }>(`/chapters/${cid}/dialogue/apply-glossary`, { method: "POST" }),
  setFrameType: (fid: string, frame_type: FrameType) =>
    request<unknown>(`/frames/${fid}`, { method: "PATCH", ...json({ frame_type }) }),

  glossary: (pid: string) => request<GlossaryTerm[]>(`/projects/${pid}/glossary`),
  createTerm: (pid: string, t: Partial<GlossaryTerm>) =>
    request<GlossaryTerm>(`/projects/${pid}/glossary`, { method: "POST", ...json(t) }),
  updateTerm: (id: string, t: Partial<GlossaryTerm>) =>
    request<GlossaryTerm>(`/glossary/${id}`, { method: "PATCH", ...json(t) }),
  deleteTerm: (id: string) => request<unknown>(`/glossary/${id}`, { method: "DELETE" }),
  mergeTerm: (id: string, into_id: string) =>
    request<GlossaryTerm>(`/glossary/${id}/merge`, { method: "POST", ...json({ into_id }) }),

  rules: (pid: string) => request<AddressRule[]>(`/projects/${pid}/address-rules`),
  createRule: (pid: string, r: Partial<AddressRule>) =>
    request<AddressRule>(`/projects/${pid}/address-rules`, { method: "POST", ...json(r) }),
  updateRule: (id: string, r: Partial<AddressRule>) =>
    request<AddressRule>(`/address-rules/${id}`, { method: "PATCH", ...json(r) }),
  deleteRule: (id: string) => request<unknown>(`/address-rules/${id}`, { method: "DELETE" }),

  characters: (pid: string) => request<Character[]>(`/projects/${pid}/characters`),
  createCharacter: (pid: string, c: Partial<Character>) =>
    request<Character>(`/projects/${pid}/characters`, { method: "POST", ...json(c) }),
  updateCharacter: (id: string, c: Partial<Character>) =>
    request<Character>(`/characters/${id}`, { method: "PATCH", ...json(c) }),
  deleteCharacter: (id: string) => request<unknown>(`/characters/${id}`, { method: "DELETE" }),
  mergeCharacter: (id: string, into_id: string) =>
    request<Character>(`/characters/${id}/merge`, { method: "POST", ...json({ into_id }) }),

  bible: (pid: string) => request<BibleData>(`/projects/${pid}/bible`),
  frameSuggestions: (chid: string) =>
    request<FrameSuggestion[]>(`/characters/${chid}/frame-suggestions`),
  outfits: (chid: string) => request<CharacterOutfit[]>(`/characters/${chid}/outfits`),
  createOutfit: (chid: string, o: Partial<CharacterOutfit>) =>
    request<CharacterOutfit>(`/characters/${chid}/outfits`, { method: "POST", ...json(o) }),
  updateOutfit: (oid: string, o: Partial<CharacterOutfit>) =>
    request<CharacterOutfit>(`/outfits/${oid}`, { method: "PATCH", ...json(o) }),
  deleteOutfit: (oid: string) => request<unknown>(`/outfits/${oid}`, { method: "DELETE" }),

  locations: (pid: string) => request<LocationItem[]>(`/projects/${pid}/locations`),
  createLocation: (pid: string, l: Partial<LocationItem>) =>
    request<LocationItem>(`/projects/${pid}/locations`, { method: "POST", ...json(l) }),
  updateLocation: (lid: string, l: Partial<LocationItem>) =>
    request<LocationItem>(`/locations/${lid}`, { method: "PATCH", ...json(l) }),
  deleteLocation: (lid: string) => request<unknown>(`/locations/${lid}`, { method: "DELETE" }),

  sheetBundleUrl: (target: "outfits" | "locations", id: string) =>
    `/api/${target}/${id}/sheet-bundle`,
  uploadSheet: (target: "outfits" | "locations", id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file, file.name);
    return request<CharacterOutfit | LocationItem>(`/${target}/${id}/sheet`, {
      method: "POST",
      body: fd,
    });
  },
  approveSheet: (target: "outfits" | "locations", id: string) =>
    request<CharacterOutfit | LocationItem>(`/${target}/${id}/sheet/approve`, { method: "POST" }),
  rejectSheet: (target: "outfits" | "locations", id: string) =>
    request<CharacterOutfit | LocationItem>(`/${target}/${id}/sheet/reject`, { method: "POST" }),
};

export const FRAME_TYPE_LABEL: Record<FrameType, string> = {
  scene: "Cảnh",
  dialogue_only: "Chỉ thoại",
  caption: "Dẫn truyện",
  sfx_only: "Chỉ hiệu ứng",
  credit: "Banner nhóm dịch",
};

export const KIND_LABEL: Record<TextKind, string> = {
  dialogue: "Thoại",
  inner_thought: "Suy nghĩ",
  narration: "Dẫn truyện",
  technique_name: "Tên chiêu",
  sfx: "Hiệu ứng âm",
  system: "Bảng hệ thống",
};

export const GENDER_LABEL: Record<Gender, string> = { male: "Nam", female: "Nữ", unknown: "?" };

export const AGE_LABEL: Record<AgeGroup, string> = {
  child: "Trẻ em",
  teen: "Thiếu niên",
  young_adult: "Thanh niên",
  middle_aged: "Trung niên",
  elderly: "Già",
  unknown: "?",
};

export const HEIGHT_CLASS_LABEL: Record<HeightClass, string> = {
  child: "Trẻ em",
  short: "Thấp",
  average: "Trung bình",
  tall: "Cao",
  giant: "Khổng lồ",
};

export const SHEET_STATUS_LABEL: Record<SheetStatus, string> = {
  missing: "Chưa có",
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
};

export const LOOK_STATUS_LABEL: Record<LookStatus, string> = {
  draft: "Bản nháp",
  approved: "Đã duyệt",
};

export const TERM_KIND_LABEL: Record<string, string> = {
  person: "Tên người",
  place: "Địa danh",
  technique: "Chiêu thức",
  realm: "Cảnh giới",
  sect: "Môn phái",
  item: "Vật phẩm",
  title: "Danh xưng",
  other: "Khác",
};
