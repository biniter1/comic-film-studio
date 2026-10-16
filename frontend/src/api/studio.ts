import { ApiError, Job, request } from "./client";

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  chapter_count?: number;
  storage_bytes?: number;
}

export type ChapterStatus =
  | "empty"
  | "imported"
  | "frames_draft"
  | "frames_approved"
  | "analyzing"
  | "dialogue_draft"
  | "dialogue_approved";

export interface Chapter {
  id: string;
  project_id: string;
  title: string;
  source_url: string | null;
  status: ChapterStatus;
  strip_width: number | null;
  created_at: string;
  updated_at: string;
  page_count: number;
  excluded_page_count: number;
  frame_count: number;
  busy_job_id: string | null;
}

export interface SourcePage {
  id: string;
  idx: number;
  original_name: string;
  width: number;
  height: number;
  status: "ok" | "excluded";
  url: string;
  preview_url: string | null;
}

export interface ImportReport {
  added: { name: string; idx: number }[];
  rejected: { name: string; reason: string }[];
  duplicates: { name: string; reason: string }[];
}

export interface StripPage {
  page_id: string;
  y0: number;
  y1: number;
  preview_url: string;
}

export interface FrameItem {
  id: string;
  idx: number;
  y0: number;
  y1: number;
  origin: "auto" | "manual";
  asset_id: string;
  url: string;
}

export interface FramesData {
  chapter_id: string;
  status: ChapterStatus;
  busy_job_id: string | null;
  strip: { width: number; height: number; pages: StripPage[] };
  frames: FrameItem[];
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export const studio = {
  listProjects: () => request<Project[]>("/projects"),
  createProject: (name: string) => request<Project>("/projects", { method: "POST", ...json({ name }) }),
  renameProject: (id: string, name: string) =>
    request<Project>(`/projects/${id}`, { method: "PATCH", ...json({ name }) }),
  deleteProject: (id: string) =>
    request<{ deleted: string }>(`/projects/${id}?confirm=true`, { method: "DELETE" }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),

  listChapters: (pid: string) => request<Chapter[]>(`/projects/${pid}/chapters`),
  createChapter: (pid: string, title: string) =>
    request<Chapter>(`/projects/${pid}/chapters`, { method: "POST", ...json({ title }) }),
  getChapter: (cid: string) => request<Chapter>(`/chapters/${cid}`),
  renameChapter: (cid: string, title: string) =>
    request<Chapter>(`/chapters/${cid}`, { method: "PATCH", ...json({ title }) }),
  deleteChapter: (cid: string) =>
    request<{ deleted: string }>(`/chapters/${cid}?confirm=true`, { method: "DELETE" }),

  importUrl: (cid: string, url: string) =>
    request<Job>(`/chapters/${cid}/import/url`, { method: "POST", ...json({ url }) }),
  importReport: (cid: string) => request<ImportReport>(`/chapters/${cid}/import/report`),
  listPages: (cid: string) => request<SourcePage[]>(`/chapters/${cid}/pages`),
  updatePages: (cid: string, pages: { id: string; excluded: boolean }[]) =>
    request<SourcePage[]>(`/chapters/${cid}/pages`, { method: "PATCH", ...json({ pages }) }),

  autoFrames: (cid: string) => request<Job>(`/chapters/${cid}/frames/auto`, { method: "POST" }),
  getFrames: (cid: string) => request<FramesData>(`/chapters/${cid}/frames`),
  putFrames: (cid: string, frames: { y0: number; y1: number }[]) =>
    request<FramesData>(`/chapters/${cid}/frames`, { method: "PUT", ...json({ frames }) }),
  approveFrames: (cid: string) =>
    request<Chapter>(`/chapters/${cid}/frames/approve`, { method: "POST" }),
};

/** Multipart upload with progress (fetch has no upload progress). */
export function uploadFiles(
  cid: string,
  files: File[],
  onProgress: (fraction: number) => void
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/chapters/${cid}/import/files`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* not json */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Job);
      else {
        const err = (body as { error?: ApiError })?.error;
        reject(
          new ApiError(
            err
              ? { code: err.code, message_vi: err.message_vi, details: err.details }
              : { code: "HTTP_ERROR", message_vi: `Tải lên thất bại (${xhr.status})`, details: {} },
            xhr.status
          )
        );
      }
    };
    xhr.onerror = () =>
      reject(new ApiError({ code: "NETWORK", message_vi: "Mất kết nối khi tải lên", details: {} }, 0));
    xhr.send(form);
  });
}

export const STATUS_LABEL: Record<ChapterStatus, string> = {
  empty: "Chưa có trang",
  imported: "Đã nhập trang",
  frames_draft: "Khung: bản nháp",
  frames_approved: "Khung: đã duyệt",
  analyzing: "Đang phân tích",
  dialogue_draft: "Thoại: bản nháp",
  dialogue_approved: "Thoại: đã duyệt",
};

export function formatBytes(n?: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

const CURRENT_KEY = "cfs.currentChapter";
export function rememberChapter(cid: string) {
  try {
    localStorage.setItem(CURRENT_KEY, cid);
  } catch {
    /* storage unavailable */
  }
}
export function lastChapter(): string | null {
  try {
    return localStorage.getItem(CURRENT_KEY);
  } catch {
    return null;
  }
}
