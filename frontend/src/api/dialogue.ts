import { Job, request } from "./client";

export type FrameType = "scene" | "dialogue_only" | "caption" | "sfx_only" | "credit";
export type TextKind = "dialogue" | "inner_thought" | "narration" | "technique_name" | "sfx" | "system";
export type Gender = "male" | "female" | "unknown";
export type AgeGroup = "child" | "teen" | "young_adult" | "middle_aged" | "elderly" | "unknown";
export type ReviewStatus = "suggested" | "approved" | "rejected";

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
  status: ReviewStatus;
  line_count?: number;
}

export interface DialogueFrame {
  id: string;
  idx: number;
  frame_type: FrameType | null;
  frame_type_source: "ai" | "user" | null;
  description: string;
  image_url: string;
}

export interface UnitInfo {
  unit_index: number;
  mode: "api" | "manual";
  status: "pending" | "awaiting_paste" | "succeeded" | "failed";
  error: string | null;
  size?: number;
}

export interface DialogueData {
  chapter_id: string;
  project_id: string;
  status: string;
  busy_job_id: string | null;
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
  Pick<DialogueLine, "text" | "speaker_key" | "speaker_label" | "kind" | "reviewed">
> & { anchor_frame_id?: string | null };

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export const dialogueApi = {
  get: (cid: string) => request<DialogueData>(`/chapters/${cid}/dialogue`),
  startApi: (cid: string, stage: Stage) =>
    request<{ jobs: Job[] }>(`/chapters/${cid}/analysis/${stage}`, {
      method: "POST",
      ...json({ mode: "api" }),
    }),
  startManual: (cid: string, stage: Stage) =>
    request<{ units: UnitInfo[] }>(`/chapters/${cid}/analysis/${stage}`, {
      method: "POST",
      ...json({ mode: "manual" }),
    }),
  units: (cid: string, stage: Stage) => request<UnitInfo[]>(`/chapters/${cid}/analysis/${stage}/units`),
  bundleUrl: (cid: string, stage: Stage, unit: number) =>
    `/api/chapters/${cid}/analysis/${stage}/bundle?unit=${unit}`,
  paste: (cid: string, stage: Stage, unit_index: number, raw: string) =>
    request<{ units: UnitInfo[] }>(`/chapters/${cid}/analysis/${stage}/paste`, {
      method: "POST",
      ...json({ unit_index, raw }),
    }),
  patchLine: (lid: string, patch: LinePatch) =>
    request<DialogueLine>(`/dialogue/${lid}`, { method: "PATCH", ...json(patch) }),
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
