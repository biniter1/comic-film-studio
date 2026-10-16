import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Combine, ImageOff, RotateCcw, Save, Scissors, Undo2 } from "lucide-react";
import { FrameItem, rememberChapter, studio } from "../api/studio";
import { Button, Empty, ErrorBox, JobProgress, PageHeader, StatusBadge } from "../components/common";
import { useJob } from "../api/useJob";

const MIN_H = 40; // must match backend validate_ranges
const STRIP_W = 380; // on-screen width of the strip column (px)

type Range = { y0: number; y1: number };

const sameRanges = (a: Range[], b: Range[]) =>
  a.length === b.length && a.every((r, i) => r.y0 === b[i].y0 && r.y1 === b[i].y1);

export function FramesPage() {
  const { cid = "" } = useParams();
  const qc = useQueryClient();
  useEffect(() => rememberChapter(cid), [cid]);

  const chapter = useQuery({ queryKey: ["chapter", cid], queryFn: () => studio.getChapter(cid) });
  const data = useQuery({ queryKey: ["frames", cid], queryFn: () => studio.getFrames(cid) });

  const serverRanges = useMemo<Range[]>(
    () => (data.data?.frames ?? []).map((f) => ({ y0: f.y0, y1: f.y1 })),
    [data.data]
  );
  const savedByKey = useMemo(() => {
    const m = new Map<string, FrameItem>();
    for (const f of data.data?.frames ?? []) m.set(`${f.y0}:${f.y1}`, f);
    return m;
  }, [data.data]);

  const [ranges, setRanges] = useState<Range[]>([]);
  const [history, setHistory] = useState<Range[][]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [splitMode, setSplitMode] = useState(false);
  useEffect(() => {
    setRanges(serverRanges);
    setHistory([]);
  }, [serverRanges]);

  const dirty = !sameRanges(ranges, serverRanges);
  const strip = data.data?.strip;
  const k = strip && strip.width ? STRIP_W / strip.width : 1;
  const stripRef = useRef<HTMLDivElement>(null);
  const frameRefs = useRef<(HTMLDivElement | null)[]>([]);

  const commit = useCallback(
    (next: Range[]) => {
      setHistory((h) => [...h.slice(-49), ranges]);
      setRanges(next);
    },
    [ranges]
  );
  const undo = useCallback(() => {
    setHistory((h) => {
      if (!h.length) return h;
      setRanges(h[h.length - 1]);
      return h.slice(0, -1);
    });
  }, []);

  const merge = (i: number) => {
    const next = [...ranges];
    next.splice(i, 2, { y0: ranges[i].y0, y1: ranges[i + 1].y1 });
    commit(next);
    setSelected(i);
  };
  const splitAt = (i: number, y: number) => {
    const r = ranges[i];
    if (y - r.y0 < MIN_H || r.y1 - y < MIN_H) return;
    const next = [...ranges];
    next.splice(i, 1, { y0: r.y0, y1: y }, { y0: y, y1: r.y1 });
    commit(next);
  };

  // --- drag a frame edge -----------------------------------------------------------
  const drag = useRef<{ i: number; edge: "top" | "bottom"; before: Range[] } | null>(null);
  const toStripY = (clientY: number) => {
    const rect = stripRef.current!.getBoundingClientRect();
    return Math.round((clientY - rect.top) / k);
  };
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const d = drag.current;
      if (!d || !strip) return;
      const y = toStripY(e.clientY);
      setRanges((cur) => {
        const next = cur.map((r) => ({ ...r }));
        const r = next[d.i];
        if (d.edge === "top") {
          const min = d.i > 0 ? next[d.i - 1].y1 : 0;
          r.y0 = Math.max(min, Math.min(y, r.y1 - MIN_H));
        } else {
          const max = d.i < next.length - 1 ? next[d.i + 1].y0 : strip.height;
          r.y1 = Math.min(max, Math.max(y, r.y0 + MIN_H));
        }
        return next;
      });
    };
    const onUp = () => {
      const d = drag.current;
      if (!d) return;
      drag.current = null;
      setRanges((cur) => {
        if (!sameRanges(cur, d.before)) setHistory((h) => [...h.slice(-49), d.before]);
        return cur;
      });
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [k, strip]);

  // --- save / approve / re-run -------------------------------------------------------
  const save = useMutation({
    mutationFn: () => studio.putFrames(cid, ranges),
    onSuccess: (d) => {
      qc.setQueryData(["frames", cid], d);
      qc.invalidateQueries({ queryKey: ["chapter", cid] });
    },
  });
  const approve = useMutation({
    mutationFn: () => studio.approveFrames(cid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chapter", cid] });
      qc.invalidateQueries({ queryKey: ["frames", cid] });
    },
  });
  const [jobId, setJobId] = useState<string | null>(null);
  const rerun = useMutation({
    mutationFn: () => studio.autoFrames(cid),
    onSuccess: (j) => setJobId(j.id),
  });
  const busyId = jobId ?? data.data?.busy_job_id ?? null;
  const job = useJob(busyId);
  const busy = !!job.data && !["succeeded", "failed", "cancelled"].includes(job.data.status);
  useEffect(() => {
    if (job.data?.status === "succeeded") qc.invalidateQueries({ queryKey: ["frames", cid] });
  }, [job.data?.status, cid, qc]);

  // keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty && !save.isPending) save.mutate();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, dirty, save]);
  // warn before leaving with unsaved edits
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const ch = chapter.data;
  const status = data.data?.status ?? ch?.status;

  return (
    <div className="p-8">
      <PageHeader
        title={ch ? `Khung · ${ch.title}` : "Khung"}
        subtitle={
          ch && (
            <span className="flex items-center gap-3">
              <Link to={`/chapters/${cid}/import`} className="hover:text-gray-200">
                ← Trang
              </Link>
              {status && <StatusBadge status={status} />}
              <span>
                {ranges.length} khung{dirty && <span className="text-amber-300"> · chưa lưu</span>}
              </span>
            </span>
          )
        }
        actions={
          <>
            <Button onClick={undo} disabled={!history.length || busy} title="Hoàn tác (Ctrl+Z)">
              <Undo2 className="w-4 h-4" /> Hoàn tác
            </Button>
            <Button
              onClick={() => setSplitMode((v) => !v)}
              disabled={busy}
              className={splitMode ? "!bg-amber-600 !text-white" : ""}
              title="Bật rồi bấm vào một khung để cắt tại vị trí đó (hoặc giữ Alt + bấm)"
            >
              <Scissors className="w-4 h-4" /> {splitMode ? "Đang ở chế độ cắt" : "Cắt khung"}
            </Button>
            <Button
              disabled={busy || rerun.isPending}
              onClick={() => {
                if (window.confirm("Cắt lại tự động sẽ thay toàn bộ khung hiện tại. Tiếp tục?")) rerun.mutate();
              }}
            >
              <RotateCcw className="w-4 h-4" /> Cắt lại tự động
            </Button>
            <Button variant="primary" disabled={!dirty || save.isPending || busy} onClick={() => save.mutate()}>
              <Save className="w-4 h-4" /> {save.isPending ? "Đang lưu…" : "Lưu (Ctrl+S)"}
            </Button>
            <Button
              variant="primary"
              disabled={dirty || busy || ranges.length === 0 || status === "frames_approved" || approve.isPending}
              title={dirty ? "Lưu thay đổi trước khi duyệt" : undefined}
              onClick={() => approve.mutate()}
              className="!bg-emerald-700 hover:!bg-emerald-600"
            >
              <CheckCircle2 className="w-4 h-4" /> {status === "frames_approved" ? "Đã duyệt" : "Duyệt khung"}
            </Button>
          </>
        }
      />
      <div className="space-y-3 mb-4 max-w-3xl">
        <ErrorBox error={data.error || save.error || approve.error || rerun.error} />
        {busy && <JobProgress job={job.data} label="Ghép & cắt khung" />}
      </div>

      {data.isLoading ? (
        <div className="text-sm text-gray-400">Đang tải…</div>
      ) : !strip || strip.pages.length === 0 ? (
        <Empty icon={<ImageOff className="w-6 h-6" />} title="Chưa có trang">
          <Link to={`/chapters/${cid}/import`} className="text-primary">
            Nhập ảnh chapter
          </Link>{" "}
          trước.
        </Empty>
      ) : (
        <div className="flex gap-6 items-start">
          {/* ---- strip editor ---- */}
          <div>
            <div className="text-xs text-gray-500 mb-2 w-[380px]">
              Kéo mép trên/dưới để chỉnh · bấm <b>Gộp</b> giữa hai khung để nối · <b>Alt + bấm</b> (hoặc chế độ cắt)
              để tách khung
            </div>
            <div
              ref={stripRef}
              data-testid="strip"
              className={`relative bg-black select-none ${splitMode ? "cursor-crosshair" : ""}`}
              style={{ width: STRIP_W, height: strip.height * k }}
            >
              {strip.pages.map((p) => (
                <img
                  key={p.page_id}
                  src={p.preview_url}
                  loading="lazy"
                  draggable={false}
                  alt=""
                  className="absolute left-0 w-full"
                  style={{ top: p.y0 * k, height: (p.y1 - p.y0) * k }}
                />
              ))}
              {ranges.map((r, i) => {
                const saved = savedByKey.has(`${r.y0}:${r.y1}`);
                return (
                  <div
                    key={`${i}-${r.y0}`}
                    ref={(el) => (frameRefs.current[i] = el)}
                    data-testid="frame-box"
                    onClick={(e) => {
                      if (busy) return;
                      if (splitMode || e.altKey) splitAt(i, toStripY(e.clientY));
                      else setSelected(i);
                    }}
                    className={`absolute left-0 w-full border-2 ${
                      selected === i ? "border-sky-400 bg-sky-400/10" : saved ? "border-primary/80" : "border-amber-400"
                    }`}
                    style={{ top: r.y0 * k, height: (r.y1 - r.y0) * k }}
                  >
                    <span className="absolute top-0 left-0 px-1.5 py-0.5 text-[10px] font-bold bg-black/75 text-white">
                      {i + 1}
                    </span>
                    {(["top", "bottom"] as const).map((edge) => (
                      <div
                        key={edge}
                        data-testid={`edge-${edge}`}
                        onPointerDown={(e) => {
                          if (busy) return;
                          e.stopPropagation();
                          drag.current = { i, edge, before: ranges };
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className={`absolute left-0 w-full h-2 cursor-ns-resize hover:bg-sky-400/60 ${
                          edge === "top" ? "-top-1" : "-bottom-1"
                        }`}
                      />
                    ))}
                  </div>
                );
              })}
              {ranges.slice(0, -1).map((r, i) => (
                <button
                  key={`m${i}`}
                  data-testid="merge-btn"
                  disabled={busy}
                  onClick={() => merge(i)}
                  className="absolute right-1 z-10 flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/80 text-[10px] text-gray-200 hover:bg-primary"
                  style={{ top: ((r.y1 + ranges[i + 1].y0) / 2) * k - 9 }}
                  title={`Gộp khung ${i + 1} và ${i + 2}`}
                >
                  <Combine className="w-3 h-3" /> Gộp
                </button>
              ))}
            </div>
          </div>

          {/* ---- frame list ---- */}
          <aside className="flex-1 min-w-[260px] sticky top-4">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-2">
              Danh sách khung
            </h2>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3 max-h-[75vh] overflow-auto pr-1">
              {ranges.map((r, i) => {
                const f = savedByKey.get(`${r.y0}:${r.y1}`);
                return (
                  <button
                    key={`l${i}-${r.y0}`}
                    onClick={() => {
                      setSelected(i);
                      frameRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" });
                    }}
                    className={`text-left rounded-lg border bg-surface overflow-hidden ${
                      selected === i ? "border-sky-400" : "border-border hover:border-primary/60"
                    }`}
                  >
                    <div className="h-28 bg-black flex items-center justify-center overflow-hidden">
                      {f ? (
                        <img src={f.url} loading="lazy" alt="" className="max-h-full max-w-full object-contain" />
                      ) : (
                        <span className="text-[11px] text-amber-300">Chưa lưu</span>
                      )}
                    </div>
                    <div className="px-2 py-1 text-[11px] text-gray-300 flex justify-between">
                      <span className="font-bold">#{i + 1}</span>
                      <span className="text-gray-500">
                        {r.y1 - r.y0}px{f?.origin === "manual" ? " · sửa tay" : ""}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
