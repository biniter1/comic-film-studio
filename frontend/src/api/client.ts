export interface ApiErrorDetail {
  code: string;
  message_vi: string;
  details: Record<string, unknown>;
}

export interface AppApiError {
  error: ApiErrorDetail;
}

export class ApiError extends Error {
  code: string;
  message_vi: string;
  details: Record<string, unknown>;
  statusCode: number;

  constructor(error: ApiErrorDetail, statusCode: number) {
    super(error.message_vi);
    this.name = "ApiError";
    this.code = error.code;
    this.message_vi = error.message_vi;
    this.details = error.details || {};
    this.statusCode = statusCode;
  }
}

export interface Job {
  id: string;
  type: string;
  status: "queued" | "running" | "waiting_user" | "succeeded" | "failed" | "cancelled";
  depends_on: string[];
  input_hash: string | null;
  attempts: number;
  max_attempts: number;
  progress: number;
  log_path: string | null;
  error_category: "transient" | "invalid_output" | "permanent" | "quota" | null;
  error_message: string | null;
  user_action_required: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SettingsData {
  data_dir: string;
  host: string;
  port: number;
  job_concurrency: number;
  max_parallel_muse_tabs: number;
  muse_clip_seconds: number;
  gemini_configured: boolean;
  ffmpeg_available: boolean;
  ffmpeg_version: string | null;
}

export interface ProviderStatus {
  providers: {
    gemini: {
      configured: boolean;
      status: string;
    };
  };
  tools: {
    ffmpeg: {
      available: boolean;
      version: string | null;
      warning: string | null;
    };
  };
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = path.startsWith("/api") ? path : `/api${path.startsWith("/") ? path : `/${path}`}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorJson: AppApiError | null = null;
    try {
      errorJson = await response.json();
    } catch {
      // Not JSON
    }

    if (errorJson && errorJson.error) {
      throw new ApiError(errorJson.error, response.status);
    }

    throw new ApiError(
      {
        code: "HTTP_ERROR",
        message_vi: `Lỗi kết nối máy chủ (${response.status})`,
        details: { statusText: response.statusText },
      },
      response.status
    );
  }

  // Handle empty or text responses
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

export const api = {
  getJobs: (status?: string) =>
    request<Job[]>(status ? `/jobs?status=${encodeURIComponent(status)}` : "/jobs"),
  createDemoJob: (payload?: { duration_s?: number; fail?: boolean; fail_category?: string }) =>
    request<Job>("/jobs/demo", {
      method: "POST",
      body: JSON.stringify(payload || {}),
    }),
  retryJob: (id: string) =>
    request<Job>(`/jobs/${id}/retry`, {
      method: "POST",
    }),
  cancelJob: (id: string) =>
    request<Job>(`/jobs/${id}/cancel`, {
      method: "POST",
    }),
  getJobLog: (id: string) =>
    request<string>(`/jobs/${id}/log`),
  getSettings: () =>
    request<SettingsData>("/settings"),
  updateSettings: (data: {
    job_concurrency?: number;
    max_parallel_muse_tabs?: number;
    muse_clip_seconds?: number;
    gemini_api_key?: string;
  }) =>
    request<SettingsData>("/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  getProvidersStatus: () =>
    request<ProviderStatus>("/settings/providers/status"),
};
