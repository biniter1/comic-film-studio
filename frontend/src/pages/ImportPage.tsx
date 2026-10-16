import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, FolderOpen, Globe, ImageOff, Save, Scissors, Upload } from "lucide-react";
import { rememberChapter, SourcePage, studio, uploadFiles } from "../api/studio";
import { Button, Empty, ErrorBox, JobProgress, PageHeader, StatusBadge } from "../components/common";
import { useJob } from "../api/useJob";

const IMAGE_EXT = /\.(jpe?g|png|webp)$/i;

/** Collect files from a drop, descending into dropped folders (Chrome/Edge). */
async function filesFromDrop(dt: DataTransfer): Promise<File[]> {
  const entries = Array.from(dt.items)
    .map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null))
    .filter(Boolean) as FileSystemEntry[];
  if (entries.length === 0) return Array.from(dt.files);
  const out: File[] = [];
  const walk = async (entry: FileSystemEntry, prefix: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
      out.push(new File([file], prefix + file.name, { type: file.type }));
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      let batch: FileSystemEntry[] = [];
      do {
        batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
        for (const e of batch) await walk(e, `${prefix}${entry.name}/`);
      } while (batch.length > 0);
    }
  };
  for (const e of entries) await walk(e, "");
  return out;
}

export function ImportPage() {
  const { cid = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  useEffect(() => rememberChapter(cid), [cid]);

  const chapter = useQuery({ queryKey: ["chapter", cid], queryFn: () => studio.getChapter(cid) });
  const pages = useQuery({ queryKey: ["pages", cid], queryFn: () => studio.listPages(cid) });
  const report = useQuery({ queryKey: ["report", cid], queryFn: () => studio.importReport(cid) });

  const [tab, setTab] = useState<"folder" | "url">("folder");
  const [url, setUrl] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobKind, setJobKind] = useState<"import" | "frames">("import");
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  // resume progress display after a reload if the chapter is busy
  useEffect(() => {
    if (!jobId && chapter.data?.busy_job_id) setJobId(chapter.data.busy_job_id);
  }, [chapter.data?.busy_job_id, jobId]);

  const job = useJob(jobId);
  useEffect(() => {
    const st = job.data?.status;
    if (!st || !["succeeded", "failed", "cancelled"].includes(st)) return;
    qc.invalidateQueries({ queryKey: ["pages", cid] });
    qc.invalidateQueries({ queryKey: ["report", cid] });
    qc.invalidateQueries({ queryKey: ["chapter", cid] });
    if (st === "succeeded" && job.data?.type === "stitch_and_cut") navigate(`/chapters/${cid}/frames`);
  }, [job.data?.status, job.data?.type, cid, qc, navigate]);

  const busy = !!job.data && !["succeeded", "failed", "cancelled"].includes(job.data.status);

  const startUpload = useMutation({
    mutationFn: async (files: File[]) => {
      const imgs = files.filter((f) => IMAGE_EXT.test(f.name));
      if (imgs.length === 0) throw new Error("Không có file ảnh (.jpg, .png, .webp) nào trong lựa chọn");
      setUploadPct(0);
      try {
        return await uploadFiles(cid, imgs, setUploadPct);
      } finally {
        setUploadPct(null);
      }
    },
    onSuccess: (j) => {
      setJobKind("import");
      setJobId(j.id);
    },
  });
  const startUrl = useMutation({
    mutationFn: () => studio.importUrl(cid, url.trim()),
    onSuccess: (j) => {
      setJobKind("import");
      setJobId(j.id);
    },
  });
  const startFrames = useMutation({
    mutationFn: () => studio.autoFrames(cid),
    onSuccess: (j) => {
      setJobKind("frames");
      setJobId(j.id);
    },
  });

  // --- local page order (drag to reorder, click to exclude) ---------------------
  const [order, setOrder] = useState<SourcePage[] | null>(null);
  useEffect(() => setOrder(null), [pages.data]);
  const list = useMemo(() => order ?? pages.data ?? [], [order, pages.data]);
  const dirty = order !== null;
  const dragIdx = useRef<number | null>(null);
  const savePages = useMutation({
    mutationFn: () =>
      studio.updatePages(
        cid,
        list.map((p) => ({ id: p.id, excluded: p.status === "excluded" }))
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pages", cid] });
      qc.invalidateQueries({ queryKey: ["chapter", cid] });
    },
  });
  const okCount = useMemo(() => list.filter((p) => p.status === "ok").length, [list]);

  const move = (from: number, to: number) => {
    if (from === to) return;
    const next = [...list];
    const [it] = next.splice(from, 1);
    next.splice(to, 0, it);
    setOrder(next);
  };
  const toggle = (i: number) => {
    const next = [...list];
    next[i] = { ...next[i], status: next[i].status === "ok" ? "excluded" : "ok" };
    setOrder(next);
  };

  const ch = chapter.data;
  const hasFrames = (ch?.frame_count ?? 0) > 0;

  return (
    <div className="p-8 max-w-7xl">
      <PageHeader
        title={ch ? `Nhập chapter · ${ch.title}` : "Nhập chapter"}
        subtitle={
          ch && (
            <span className="flex items-center gap-3">
              <Link to={`/projects/${ch.project_id}`} className="hover:text-gray-200">
                ← Dự án
              </Link>
              <StatusBadge status={ch.status} />
              <span>{okCount} trang dùng</span>
            </span>
          )
        }
        actions={
          <Button
            variant="primary"
            disabled={busy || dirty || okCount === 0 || startFrames.isPending}
            title={dirty ? "Lưu thứ tự trang trước" : undefined}
            onClick={() => {
              if (hasFrames && !window.confirm("Cắt lại sẽ thay toàn bộ khung hiện có. Tiếp tục?")) return;
              startFrames.mutate();
            }}
          >
            <Scissors className="w-4 h-4" /> Ghép & cắt khung
          </Button>
        }
      />

      <div className="grid lg:grid-cols-[380px_1fr] gap-6">
        {/* ---- source ---- */}
        <section className="space-y-4">
          <div className="flex rounded-lg border border-border overflow-hidden text-sm">
            {(
              [
                ["folder", "Từ thư mục", FolderOpen],
                ["url", "Từ URL", Globe],
              ] as const
            ).map(([k, label, Icon]) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                className={`flex-1 flex items-center justify-center gap-2 py-2 ${
                  tab === k ? "bg-primary text-white" : "bg-surface text-gray-300 hover:bg-surface-raised"
                }`}
              >
                <Icon className="w-4 h-4" /> {label}
              </button>
            ))}
          </div>

          {tab === "folder" ? (
            <div
              data-testid="dropzone"
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={async (e) => {
                e.preventDefault();
                setDragOver(false);
                if (busy) return;
                startUpload.mutate(await filesFromDrop(e.dataTransfer));
              }}
              className={`rounded-xl border-2 border-dashed p-6 text-center transition ${
                dragOver ? "border-primary bg-primary/10" : "border-border bg-surface"
              }`}
            >
              <Upload className="w-8 h-8 mx-auto text-gray-400" />
              <div className="mt-2 text-sm text-gray-200">Kéo-thả ảnh hoặc cả thư mục chapter vào đây</div>
              <div className="text-xs text-gray-500 mt-1">JPG / PNG / WEBP · sắp xếp theo tên (1, 2, 10…)</div>
              <div className="mt-4 flex justify-center gap-2">
                <Button disabled={busy} onClick={() => fileInput.current?.click()}>
                  Chọn ảnh
                </Button>
                <Button disabled={busy} onClick={() => folderInput.current?.click()}>
                  Chọn thư mục
                </Button>
              </div>
              <input
                ref={fileInput}
                type="file"
                multiple
                accept=".jpg,.jpeg,.png,.webp"
                className="hidden"
                data-testid="file-input"
                onChange={(e) => {
                  if (e.target.files) startUpload.mutate(Array.from(e.target.files));
                  e.target.value = "";
                }}
              />
              <input
                ref={folderInput}
                type="file"
                multiple
                className="hidden"
                // @ts-expect-error non-standard but supported by Chromium/Edge/Firefox
                webkitdirectory=""
                onChange={(e) => {
                  if (e.target.files) startUpload.mutate(Array.from(e.target.files));
                  e.target.value = "";
                }}
              />
            </div>
          ) : (
            <form
              className="rounded-xl border border-border bg-surface p-4 space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (url.trim()) startUrl.mutate();
              }}
            >
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://… (link trang đọc chapter)"
                className="w-full rounded-lg bg-background border border-border px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:outline-none focus:border-primary"
              />
              <Button variant="primary" type="submit" disabled={busy || !url.trim()}>
                <Globe className="w-4 h-4" /> Tải ảnh từ trang
              </Button>
              <p className="text-xs text-gray-500">
                Chỉ dùng với nguồn bạn được phép truy cập. Trang cần đăng nhập hoặc chặn tải tự động → dùng
                "Từ thư mục".
              </p>
            </form>
          )}

          {uploadPct !== null && (
            <div className="rounded-lg border border-border bg-surface p-3 text-sm">
              <div className="text-gray-300 mb-2">Đang tải file lên… {Math.round(uploadPct * 100)}%</div>
              <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
                <div className="h-full bg-sky-500" style={{ width: `${uploadPct * 100}%` }} />
              </div>
            </div>
          )}
          <JobProgress
            job={job.data}
            label={jobKind === "frames" || job.data?.type === "stitch_and_cut" ? "Ghép & cắt khung" : "Nhập ảnh"}
          />
          <ErrorBox error={startUpload.error || startUrl.error || startFrames.error || savePages.error} />

          {report.data && (report.data.rejected.length > 0 || report.data.duplicates.length > 0) && (
            <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-3 text-xs space-y-1 max-h-64 overflow-auto">
              <div className="font-medium text-amber-200 mb-1">Lần nhập gần nhất</div>
              {report.data.rejected.map((r, i) => (
                <div key={`r${i}`} className="text-red-300">
                  ✗ <span className="font-mono">{r.name}</span> — {r.reason}
                </div>
              ))}
              {report.data.duplicates.map((r, i) => (
                <div key={`d${i}`} className="text-amber-300">
                  ≈ <span className="font-mono">{r.name}</span> — {r.reason}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ---- pages grid ---- */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">
              Trang ({list.length})
            </h2>
            <span className="text-xs text-gray-500">Kéo để đổi thứ tự · bấm con mắt để bỏ/dùng lại trang</span>
            {dirty && (
              <div className="ml-auto flex gap-2">
                <Button onClick={() => setOrder(null)}>Hủy</Button>
                <Button
                  variant="primary"
                  disabled={savePages.isPending}
                  onClick={() => {
                    if (hasFrames && !window.confirm("Đổi trang sẽ xóa các khung đã cắt (cần cắt lại). Tiếp tục?"))
                      return;
                    savePages.mutate();
                  }}
                >
                  <Save className="w-4 h-4" /> Lưu thứ tự
                </Button>
              </div>
            )}
          </div>
          {pages.isLoading ? (
            <div className="text-sm text-gray-400">Đang tải…</div>
          ) : list.length === 0 ? (
            <Empty icon={<ImageOff className="w-6 h-6" />} title="Chưa có trang nào">
              Nhập ảnh từ thư mục hoặc URL ở bên trái.
            </Empty>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3" data-testid="page-grid">
              {list.map((p, i) => (
                <div
                  key={p.id}
                  draggable
                  onDragStart={() => (dragIdx.current = i)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (dragIdx.current !== null) move(dragIdx.current, i);
                    dragIdx.current = null;
                  }}
                  className={`group relative rounded-lg border bg-surface overflow-hidden cursor-grab ${
                    p.status === "excluded" ? "border-border opacity-40" : "border-border hover:border-primary/60"
                  }`}
                >
                  <div className="aspect-[3/5] bg-black overflow-hidden">
                    {p.preview_url && (
                      <img src={p.preview_url} loading="lazy" className="w-full object-cover object-top" alt="" />
                    )}
                  </div>
                  <div className="px-2 py-1.5 text-[11px] text-gray-300 flex items-center gap-1">
                    <span className="font-mono text-gray-500">{String(i + 1).padStart(3, "0")}</span>
                    <span className="truncate" title={p.original_name}>
                      {p.original_name}
                    </span>
                  </div>
                  <button
                    title={p.status === "ok" ? "Bỏ trang này" : "Dùng lại trang"}
                    onClick={() => toggle(i)}
                    className="absolute top-1.5 right-1.5 p-1 rounded bg-black/60 text-gray-200 opacity-0 group-hover:opacity-100"
                  >
                    {p.status === "ok" ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
