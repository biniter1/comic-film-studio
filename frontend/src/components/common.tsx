import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { ReactNode } from "react";
import { ApiError, Job } from "../api/client";
import { ChapterStatus, STATUS_LABEL } from "../api/studio";

export function JobProgress({ job, label }: { job: Job | undefined; label: string }) {
  if (!job) return null;
  const pct = Math.round((job.progress || 0) * 100);
  const failed = job.status === "failed";
  const done = job.status === "succeeded";
  return (
    <div className="rounded-lg border border-border bg-surface p-3 text-sm" data-testid="job-progress">
      <div className="flex items-center gap-2 mb-2">
        {done ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
        ) : failed ? (
          <XCircle className="w-4 h-4 text-red-400" />
        ) : (
          <Loader2 className="w-4 h-4 text-primary animate-spin" />
        )}
        <span className="font-medium text-gray-200">{label}</span>
        <span className="ml-auto text-xs text-gray-400 font-mono">
          {job.id} · {done ? "xong" : failed ? "lỗi" : job.status === "queued" ? "đang chờ" : `${pct}%`}
        </span>
      </div>
      {!done && !failed && (
        <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
          <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
      {failed && (
        <div className="text-red-300 text-xs space-y-1">
          <div>{job.error_message}</div>
          {job.user_action_required && (
            <div className="text-amber-300">→ {job.user_action_required}</div>
          )}
        </div>
      )}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg =
    error instanceof ApiError ? error.message_vi : error instanceof Error ? error.message : String(error);
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-200">
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
      <span>{msg}</span>
    </div>
  );
}

const BADGE: Record<ChapterStatus, string> = {
  empty: "bg-gray-700/60 text-gray-300",
  imported: "bg-sky-900/60 text-sky-200",
  frames_draft: "bg-amber-900/60 text-amber-200",
  frames_approved: "bg-emerald-900/60 text-emerald-200",
};

export function StatusBadge({ status }: { status: ChapterStatus }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${BADGE[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold text-gray-100 truncate">{title}</h1>
        {subtitle && <div className="text-sm text-gray-400 mt-1">{subtitle}</div>}
      </div>
      <div className="ml-auto flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}

export function Button({
  children,
  variant = "secondary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-primary hover:bg-primary-hover text-white",
    secondary: "bg-surface-raised hover:bg-gray-700 text-gray-200 border border-border",
    danger: "bg-red-900/60 hover:bg-red-800 text-red-100 border border-red-800",
  }[variant];
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition disabled:opacity-40 disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="border border-dashed border-border rounded-xl p-10 text-center text-gray-400">
      <div className="inline-flex w-12 h-12 items-center justify-center rounded-full bg-surface-raised mb-3 text-gray-300">
        {icon}
      </div>
      <div className="text-gray-200 font-medium">{title}</div>
      {children && <div className="text-sm mt-1">{children}</div>}
    </div>
  );
}
