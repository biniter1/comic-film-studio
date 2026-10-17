import { Job, request } from "./client";

export interface Camera {
  shot_size: string;
  movement: string;
  speed: string;
  angle: string;
}
export interface Blocking {
  character_key: string;
  outfit_key?: string | null;
  screen_pos: "left" | "center" | "right";
  depth: "fg" | "mg" | "bg";
  facing: "left" | "right" | "camera" | "away";
  pose: string;
}
export interface Beat {
  t0: number;
  t1: number;
  action: string;
}
export interface Attachment {
  kind: "frame" | "char_sheet" | "location_sheet";
  asset_id: string;
  label: string;
  url: string;
}
export interface ShotLine {
  id: string;
  kind: string;
  text: string;
  speaker: string | null;
}
export interface Shot {
  id: string;
  scene_id: string;
  code: string;
  order: number;
  chain_code: string;
  chain_pos: number;
  transition_in: "cut" | "continuous" | "match";
  frame_ids: string[];
  duration_s: number;
  camera: Camera;
  location_key: string | null;
  blocking: Blocking[];
  beats: Beat[];
  start_state: string;
  end_state: string;
  action: string;
  emotion: string;
  titles: { text: string; style: string }[];
  sfx_notes: string;
  inserted: boolean;
  keyframe_prompt: string;
  video_prompt: string;
  attachments: Attachment[];
  prompt_override: { keyframe?: string; video?: string };
  rule_notes: string[];
  edited_by: "ai" | "user";
  lines: ShotLine[];
}
export interface Scene {
  id: string;
  code: string;
  order: number;
  summary: string;
  frame_ids: string[];
  location_key: string | null;
  mood: string | null;
}
export interface ShotsData {
  chapter_id: string;
  project_id: string;
  status: string;
  busy_job_id: string | null;
  frames: { id: string; idx: number; frame_type: string | null; image_url: string }[];
  scenes: Scene[];
  shots: Shot[];
  characters: { key: string; name: string; role: string; is_group: boolean; outfits: string[] }[];
  locations: { key: string; name_vi: string; location_lock: string | null }[];
  units: Record<"plan" | "shots", { unit_index: number; status: string; mode: string; error: string | null }[]>;
}
export type ShotPatch = Partial<
  Pick<Shot, "transition_in" | "duration_s" | "camera" | "blocking" | "beats" | "start_state" | "end_state" | "action">
> & { prompt_override?: { keyframe?: string | null; video?: string | null } };

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export const shotsApi = {
  get: (cid: string) => request<ShotsData>(`/chapters/${cid}/shots`),
  plan: (cid: string, force_all = false) =>
    request<{ jobs: Job[] }>(`/chapters/${cid}/analysis/plan`, {
      method: "POST",
      ...json({ mode: "api", force_all, then_shots: true }),
    }),
  patch: (sid: string, patch: ShotPatch) =>
    request<Shot>(`/shots/${sid}`, { method: "PATCH", ...json(patch) }),
  approve: (cid: string) =>
    request<{ status: string }>(`/chapters/${cid}/shots/approve-plan`, { method: "POST" }),
};

export const SHOT_SIZES = ["extreme_wide", "wide", "full", "medium", "medium_close_up", "close_up", "extreme_close_up", "insert"];
export const MOVEMENTS = [
  "static", "push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "truck_left",
  "truck_right", "orbit_left", "orbit_right", "follow", "crane_up", "crane_down", "handheld_shake", "crash_zoom",
];
export const SPEEDS = ["slow", "medium", "fast"];
export const ANGLES = ["eye", "low", "high", "overhead", "dutch"];
export const SIZE_VI: Record<string, string> = {
  extreme_wide: "Toàn cảnh xa", wide: "Toàn cảnh", full: "Toàn thân", medium: "Trung cảnh",
  medium_close_up: "Cận trung", close_up: "Cận cảnh", extreme_close_up: "Đặc tả", insert: "Chi tiết",
};
export const MOVE_VI: Record<string, string> = {
  static: "Đứng yên", push_in: "Đẩy vào", pull_out: "Kéo ra", pan_left: "Lia trái", pan_right: "Lia phải",
  tilt_up: "Ngước lên", tilt_down: "Cúi xuống", truck_left: "Trượt trái", truck_right: "Trượt phải",
  orbit_left: "Xoay quanh trái", orbit_right: "Xoay quanh phải", follow: "Bám theo", crane_up: "Cẩu lên",
  crane_down: "Cẩu xuống", handheld_shake: "Rung tay", crash_zoom: "Zoom giật",
};
