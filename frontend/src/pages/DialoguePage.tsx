import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  CheckCircle2,
  ClipboardPaste,
  Download,
  Eye,
  Hand,
  RotateCcw,
  Sparkles,
  SpellCheck,
  Trash2,
  Wand2,
} from "lucide-react";
import {
  Character,
  DialogueData,
  DialogueFrame,
  DialogueLine,
  FRAME_TYPE_LABEL,
  FrameType,
  GENDER_LABEL,
  AGE_LABEL,
  KIND_LABEL,
  LinePatch,
  Stage,
  TextKind,
  UnitInfo,
  dialogueApi,
} from "../api/dialogue";
import { rememberChapter, studio } from "../api/studio";
import { useJob } from "../api/useJob";
import { Button, Empty, ErrorBox, JobProgress, PageHeader, StatusBadge } from "../components/common";

const LOW_CONF = 0.7;
const TERMINAL = ["succeeded", "failed", "cancelled"];

type Filter = { review: boolean; hasNote: boolean; speaker: string; frame: string };

export function DialoguePage() {
  const { cid = "" } = useParams();
  const qc = useQueryClient();
  useEffect(() => rememberChapter(cid), [cid]);

  const chapter = useQuery({ queryKey: ["chapter", cid], queryFn: () => studio.getChapter(cid) });
  const data = useQuery({ queryKey: ["dialogue", cid], queryFn: () => dialogueApi.get(cid) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["dialogue", cid] });
    qc.invalidateQueries({ queryKey: ["chapter", cid] });
  };

  // --- jobs ------------------------------------------------------------------
  const [jobIds, setJobIds] = useState<string[]>([]);
  const start = useMutation({
    mutationFn: ({ stage, force_all }: { stage: Stage; force_all?: boolean }) =>
      dialogueApi.startApi(cid, stage, { force_all }),
    onSuccess: (r) => {
      setJobIds(r.jobs.map((j) => j.id));
      setManual(null);
    },
  });
  const ids = jobIds.length ? jobIds : data.data?.busy_job_id ? [data.data.busy_job_id] : [];
  const job0 = useJob(ids[0]);
  const job1 = useJob(ids[1]);
  const jobs = [job0.data, job1.data].filter(Boolean);
  const busy = jobs.some((j) => j && !TERMINAL.includes(j.status) && !(j.status === "queued" && j.user_action_required));
  const jobKey = jobs.map((j) => j?.status).join(",");
  useEffect(() => {
    if (jobKey) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobKey]);

  // --- manual mode ---------------------------------------------------------------
  const [manual, setManual] = useState<Stage | null>(null);
  const startManual = useMutation({
    mutationFn: ({ stage, force_all }: { stage: Stage; force_all?: boolean }) =>
      dialogueApi.startManual(cid, stage, { force_all }),
    onSuccess: (_r, vars) => {
      setManual(vars.stage);
      refresh();
    },
  });

  const d = data.data;
  const status = d?.status ?? chapter.data?.status;
  const hasScript = status === "dialogue_draft" || status === "dialogue_approved";
  const canAnalyze = ["frames_approved", "analyzing", "dialogue_draft", "dialogue_approved"].includes(status ?? "");

  const approve = useMutation({ mutationFn: () => dialogueApi.approve(cid), onSuccess: refresh });
  const reviewAll = useMutation({ mutationFn: () => dialogueApi.reviewAll(cid), onSuccess: refresh });
  const applyGlossary = useMutation({ mutationFn: () => dialogueApi.applyGlossary(cid), onSuccess: refresh });

  const [filter, setFilter] = useState<Filter>({ review: false, hasNote: false, speaker: "", frame: "" });
  const lines = useMemo(() => {
    let ls = d?.lines ?? [];
    if (filter.review) ls = ls.filter((l) => needsAttention(l));
    if (filter.hasNote) ls = ls.filter((l) => Boolean(l.edit_note && l.edit_note.trim()));
    if (filter.speaker) ls = ls.filter((l) => (l.speaker_key ?? `label:${l.speaker_label ?? ""}`) === filter.speaker);
    if (filter.frame) ls = ls.filter((l) => l.source_frame_id === filter.frame || l.anchor_frame_id === filter.frame);
    return ls;
  }, [d, filter]);

  const frameById = useMemo(() => new Map((d?.frames ?? []).map((f) => [f.id, f])), [d]);
  const ch = chapter.data;
  const pending = d?.stats.pending_review ?? 0;
  const readProgress = d?.read_progress;
  const totalUnits = readProgress?.total ?? 0;
  const succeededUnits = readProgress?.succeeded ?? 0;
  const unreadFrames = readProgress?.unread_frames ?? 0;

  const handleRereadAll = () => {
    const est = totalUnits || 1;
    if (window.confirm(`Sẽ gọi AI lại cho tất cả ${totalUnits} gói, ước tính ~${est} credit. Tiếp tục?`)) {
      start.mutate({ stage: "read", force_all: true });
    }
  };

  const handleRepolishAll = () => {
    if (window.confirm("Sẽ gọi AI biên tập lại toàn bộ câu thoại (trừ câu bạn đã sửa tay). Tiếp tục?")) {
      start.mutate({ stage: "dialogue", force_all: true });
    }
  };

  return (
    <div className="p-8">
      <PageHeader
        title={ch ? `Kịch bản thoại · ${ch.title}` : "Kịch bản thoại"}
        subtitle={
          ch && (
            <span className="flex flex-wrap items-center gap-3">
              <Link to={`/chapters/${cid}/frames`} className="hover:text-gray-200">
                ← Khung
              </Link>
              {status && <StatusBadge status={status as never} />}
              {unreadFrames > 0 && (
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20"
                  data-testid="unread-frames-badge"
                >
                  Còn {unreadFrames} khung chưa đọc
                </span>
              )}
              {unreadFrames === 0 && totalUnits > 0 && (
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded bg-gray-800 text-sky-300 border border-gray-700"
                  data-testid="read-progress-badge"
                >
                  Đã đọc {succeededUnits}/{totalUnits} gói
                </span>
              )}
              {d && d.stats.lines > 0 && (
                <span data-testid="dialogue-stats">
                  {d.stats.lines} câu · AI sửa {d.stats.edited_ai} · bạn sửa {d.stats.edited_user}
                  {pending > 0 && <span className="text-amber-300"> · {pending} câu cần soát</span>}
                </span>
              )}
              {d && (
                <Link to={`/projects/${d.project_id}/glossary`} className="text-primary hover:underline">
                  <BookOpen className="inline w-3.5 h-3.5 mr-1" />
                  Thuật ngữ & nhân vật
                </Link>
              )}
            </span>
          )
        }
        actions={
          <>
            <Button
              variant="primary"
              disabled={!canAnalyze || busy || start.isPending}
              onClick={() => start.mutate({ stage: "read", force_all: false })}
              data-testid="analyze-btn"
              title={
                unreadFrames > 0
                  ? `Đọc ${unreadFrames} khung còn lại (không gọi lại phần việc đã xong)`
                  : "Chạy tiếp các gói còn thiếu (không gọi lại phần việc đã xong)"
              }
            >
              <Sparkles className="w-4 h-4" />{" "}
              {unreadFrames > 0
                ? `Đọc ${unreadFrames} khung còn lại`
                : succeededUnits > 0 && succeededUnits < totalUnits
                ? "Chạy tiếp"
                : succeededUnits > 0 && succeededUnits === totalUnits
                ? "Phân tích"
                : hasScript
                ? "Phân tích lại"
                : "Phân tích bằng Gemini"}
            </Button>
            {(succeededUnits > 0 || hasScript) && (
              <Button
                disabled={!canAnalyze || busy || start.isPending}
                onClick={handleRereadAll}
                data-testid="reread-all-btn"
                title="Xóa kết quả cũ và gọi AI đọc lại toàn bộ các gói"
              >
                <RotateCcw className="w-4 h-4" /> Đọc lại toàn bộ (tốn credit)
              </Button>
            )}
            {hasScript && (
              <>
                <Button
                  disabled={busy || start.isPending}
                  onClick={() => start.mutate({ stage: "dialogue", force_all: false })}
                  title="Chỉ gửi các câu chưa có bản biên tập (chưa từng được AI xử lý) hoặc câu mới"
                  data-testid="dialogue-btn"
                >
                  <Wand2 className="w-4 h-4" /> Biên tập
                </Button>
                <Button
                  disabled={busy || start.isPending}
                  onClick={handleRepolishAll}
                  title="Biên tập lại toàn bộ câu thoại (không đụng câu bạn đã sửa tay)"
                  data-testid="repolish-all-btn"
                >
                  <RotateCcw className="w-4 h-4" /> Biên tập lại toàn bộ
                </Button>
              </>
            )}
            <Button
              disabled={!canAnalyze || busy}
              onClick={() => setManual((m) => (m ? null : hasScript ? "dialogue" : "read"))}
              title="Không dùng API: tải gói về, dán vào Gemini trên web rồi dán kết quả lại"
            >
              <Hand className="w-4 h-4" /> Chế độ thủ công
            </Button>
            {hasScript && (
              <>
                <Button
                  disabled={busy || applyGlossary.isPending}
                  onClick={() => applyGlossary.mutate()}
                  title="Thay mọi biến thể sai bằng thuật ngữ chuẩn đã duyệt (không đụng câu bạn sửa tay)"
                >
                  <SpellCheck className="w-4 h-4" /> Áp thuật ngữ
                </Button>
                <Button
                  variant="primary"
                  className="!bg-emerald-700 hover:!bg-emerald-600"
                  disabled={busy || pending > 0 || status === "dialogue_approved" || approve.isPending}
                  title={pending > 0 ? `Còn ${pending} câu cần soát` : undefined}
                  onClick={() => approve.mutate()}
                  data-testid="approve-dialogue"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  {status === "dialogue_approved" ? "Đã duyệt" : "Duyệt kịch bản thoại"}
                </Button>
              </>
            )}
          </>
        }
      />

      <div className="space-y-3 mb-4 max-w-4xl">
        <ErrorBox
          error={data.error || start.error || startManual.error || approve.error || reviewAll.error || applyGlossary.error}
        />
        {applyGlossary.data && (
          <div className="text-xs text-emerald-300">Đã chuẩn hóa thuật ngữ ở {applyGlossary.data.changed} câu.</div>
        )}
        {jobs.map(
          (j) =>
            j && (
              <JobProgress
                key={j.id}
                job={j}
                label={j.type === "analysis_read" ? "Đọc truyện & bóc thoại" : "Biên tập thoại"}
              />
            )
        )}
        {!canAnalyze && status && (
          <div className="text-sm text-amber-300">
            Hãy{" "}
            <Link to={`/chapters/${cid}/frames`} className="underline">
              duyệt khung
            </Link>{" "}
            trước khi phân tích.
          </div>
        )}
        {manual && d && (
          <ManualPanel
            cid={cid}
            stage={manual}
            setStage={setManual}
            units={d.units[manual]}
            hasScript={hasScript}
            onStart={(s) => startManual.mutate({ stage: s, force_all: false })}
            starting={startManual.isPending}
            onDone={refresh}
          />
        )}
      </div>

      {data.isLoading ? (
        <div className="text-sm text-gray-400">Đang tải…</div>
      ) : !d || d.lines.length === 0 ? (
        <Empty icon={<Sparkles className="w-6 h-6" />} title="Chưa có kịch bản thoại">
          {canAnalyze ? "Bấm “Phân tích bằng Gemini” hoặc dùng chế độ thủ công." : "Duyệt khung trước."}
        </Empty>
      ) : (
        <div className="flex gap-6 items-start">
          <FrameColumn
            data={d}
            selected={filter.frame}
            onSelect={(f) => setFilter((x) => ({ ...x, frame: x.frame === f ? "" : f }))}
            busy={busy}
            onChanged={refresh}
          />
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-3 mb-3 text-sm">
              <label className="flex items-center gap-1.5 text-gray-300">
                <input
                  type="checkbox"
                  checked={filter.review}
                  onChange={(e) => setFilter((x) => ({ ...x, review: e.target.checked }))}
                  data-testid="filter-review"
                />
                Chỉ câu cần soát
              </label>
              <label className="flex items-center gap-1.5 text-gray-300">
                <input
                  type="checkbox"
                  checked={filter.hasNote}
                  onChange={(e) => setFilter((x) => ({ ...x, hasNote: e.target.checked }))}
                  data-testid="filter-has-note"
                />
                Chỉ câu AI đổi nghĩa
              </label>
              <select
                className="bg-surface border border-border rounded px-2 py-1 text-sm"
                value={filter.speaker}
                onChange={(e) => setFilter((x) => ({ ...x, speaker: e.target.value }))}
              >
                <option value="">Mọi người nói</option>
                {d.characters.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
              </select>
              {filter.frame && (
                <button className="text-primary text-xs" onClick={() => setFilter((x) => ({ ...x, frame: "" }))}>
                  Khung #{frameById.get(filter.frame)?.idx} × bỏ lọc
                </button>
              )}
              {pending > 0 && (
                <Button className="ml-auto" disabled={reviewAll.isPending || busy} onClick={() => reviewAll.mutate()}>
                  <Eye className="w-4 h-4" /> Đánh dấu đã xem tất cả
                </Button>
              )}
            </div>
            <div className="rounded-xl border border-border bg-surface divide-y divide-border" data-testid="line-list">
              {lines.map((l) => (
                <LineRow
                  key={l.id}
                  line={l}
                  frames={d.frames}
                  source={frameById.get(l.source_frame_id)}
                  characters={d.characters}
                  disabled={busy}
                  onChanged={refresh}
                />
              ))}
              {lines.length === 0 && <div className="p-4 text-sm text-gray-400">Không có câu nào khớp bộ lọc.</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function needsAttention(l: DialogueLine) {
  return (l.needs_review && !l.reviewed) || (isSpoken(l.kind) && l.speaker_confidence < LOW_CONF);
}

const isSpoken = (k: TextKind) => k === "dialogue" || k === "inner_thought";

// ---------------------------------------------------------------------------------------
function FrameColumn({
  data,
  selected,
  onSelect,
  busy,
  onChanged,
}: {
  data: DialogueData;
  selected: string;
  onSelect: (fid: string) => void;
  busy: boolean;
  onChanged: () => void;
}) {
  const setType = useMutation({
    mutationFn: ({ fid, t }: { fid: string; t: FrameType }) => dialogueApi.setFrameType(fid, t),
    onSuccess: onChanged,
  });
  const drop = useMutation({
    mutationFn: async (fid: string) => {
      const fr = await studio.getFrames(data.chapter_id);
      return studio.putFrames(
        data.chapter_id,
        fr.frames.filter((f) => f.id !== fid).map((f) => ({ y0: f.y0, y1: f.y1 }))
      );
    },
    onSuccess: onChanged,
  });
  const count = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of data.lines) m.set(l.anchor_frame_id ?? "", (m.get(l.anchor_frame_id ?? "") ?? 0) + 1);
    return m;
  }, [data.lines]);

  return (
    <div className="w-56 shrink-0 space-y-2 sticky top-0 max-h-[calc(100vh-8rem)] overflow-y-auto pr-1">
      <ErrorBox error={setType.error || drop.error} />
      {data.frames.map((f) => (
        <div
          key={f.id}
          data-testid="dlg-frame"
          className={`rounded-lg border p-1.5 bg-surface ${
            selected === f.id ? "border-primary" : f.frame_type === "credit" ? "border-red-800" : "border-border"
          }`}
        >
          <button className="block w-full" onClick={() => onSelect(f.id)} title={f.description}>
            <img src={f.image_url} alt="" className="w-full max-h-40 object-cover object-top rounded" loading="lazy" />
          </button>
          <div className="flex items-center gap-1 mt-1 text-[11px]">
            <span className="font-mono text-gray-400">#{f.idx}</span>
            <select
              className="flex-1 min-w-0 bg-surface-raised border border-border rounded px-1 py-0.5"
              value={f.frame_type ?? ""}
              disabled={busy}
              data-testid="frame-type"
              onChange={(e) => setType.mutate({ fid: f.id, t: e.target.value as FrameType })}
            >
              {!f.frame_type && <option value="">(chưa phân loại)</option>}
              {Object.entries(FRAME_TYPE_LABEL).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
            {count.get(f.id) ? <span className="text-gray-400">{count.get(f.id)}💬</span> : null}
          </div>
          {f.frame_type === "credit" && (
            <button
              className="mt-1 w-full text-[11px] rounded bg-red-900/60 hover:bg-red-800 text-red-100 py-0.5"
              disabled={busy || drop.isPending}
              onClick={() => window.confirm(`Bỏ khung #${f.idx} khỏi chapter?`) && drop.mutate(f.id)}
            >
              <Trash2 className="inline w-3 h-3 mr-1" />
              Bỏ khung
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
function LineRow({
  line,
  frames,
  source,
  characters,
  disabled,
  onChanged,
}: {
  line: DialogueLine;
  frames: DialogueFrame[];
  source?: DialogueFrame;
  characters: Character[];
  disabled: boolean;
  onChanged: () => void;
}) {
  const [text, setText] = useState(line.text);
  useEffect(() => setText(line.text), [line.text]);
  const patch = useMutation({
    mutationFn: (p: LinePatch) => dialogueApi.patchLine(line.id, p),
    onSuccess: onChanged,
  });
  const revert = useMutation({ mutationFn: () => dialogueApi.revertLine(line.id), onSuccess: onChanged });

  const lowConf = isSpoken(line.kind) && line.speaker_confidence < LOW_CONF;
  const flagged = line.needs_review && !line.reviewed;
  const speakerValue = line.speaker_key ?? (line.speaker_label ? "__label" : "");
  const sceneFrames = frames.filter((f) => f.frame_type === "scene" || f.frame_type === null);
  const anchor = frames.find((f) => f.id === line.anchor_frame_id);

  return (
    <div
      data-testid="line-row"
      className={`flex gap-3 p-3 ${flagged ? "bg-amber-950/30" : ""}`}
      title={line.edit_note ?? undefined}
    >
      {source && (
        <img
          src={source.image_url}
          alt=""
          className="w-16 h-16 object-cover object-top rounded border border-border shrink-0"
          loading="lazy"
        />
      )}
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono text-gray-500">{line.order}.</span>
          <select
            data-testid="speaker-select"
            className={`bg-surface-raised border rounded px-1.5 py-0.5 ${
              lowConf ? "border-amber-500 text-amber-200" : "border-border"
            }`}
            value={speakerValue}
            disabled={disabled}
            title={lowConf ? `AI không chắc (${Math.round(line.speaker_confidence * 100)}%)` : undefined}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "__label") {
                const label = window.prompt("Tên người nói (nhân vật phụ)", line.speaker_label ?? "");
                if (label !== null) patch.mutate({ speaker_key: null, speaker_label: label.trim() || null });
              } else patch.mutate({ speaker_key: v || null, ...(v ? {} : { speaker_label: null }) });
            }}
          >
            <option value="">(không ai / dẫn truyện)</option>
            {characters.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
            <option value="__label">{line.speaker_label ? `Nhân vật phụ: ${line.speaker_label}` : "Nhân vật phụ…"}</option>
          </select>
          <span className="text-gray-500">
            {GENDER_LABEL[line.speaker_gender]} · {AGE_LABEL[line.speaker_age]}
          </span>
          <select
            className="bg-surface-raised border border-border rounded px-1.5 py-0.5"
            value={line.kind}
            disabled={disabled}
            onChange={(e) => patch.mutate({ kind: e.target.value as TextKind })}
          >
            {Object.entries(KIND_LABEL).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
          <span className="text-gray-500">gắn vào</span>
          <select
            className={`bg-surface-raised border rounded px-1.5 py-0.5 ${
              line.anchor_locked ? "border-primary" : "border-border"
            }`}
            value={line.anchor_frame_id ?? ""}
            disabled={disabled}
            title={line.anchor_locked ? "Bạn đã chọn tay" : "Tự động theo loại khung"}
            data-testid="anchor-select"
            onChange={(e) => patch.mutate({ anchor_frame_id: e.target.value || null })}
          >
            <option value="">{line.anchor_locked ? "↺ tự động" : anchor ? `khung #${anchor.idx}` : "(không có)"}</option>
            {sceneFrames.map((f) => (
              <option key={f.id} value={f.id}>
                khung #{f.idx}
              </option>
            ))}
          </select>
          {line.edited_by !== "none" && (
            <span
              className={`px-1.5 rounded ${
                line.edited_by === "user" ? "bg-sky-900/60 text-sky-200" : "bg-violet-900/60 text-violet-200"
              }`}
            >
              {line.edited_by === "user" ? "bạn sửa" : "AI sửa"}
            </span>
          )}
          {flagged && (
            <button
              className="px-1.5 rounded bg-amber-800/70 text-amber-100"
              onClick={() => patch.mutate({ reviewed: true })}
              title={line.edit_note ?? "Cần soát lại"}
              data-testid="mark-reviewed"
            >
              cần soát · đã xem ✓
            </button>
          )}
        </div>
        {line.text_raw !== line.text && (
          <div className="text-xs text-gray-500 line-through decoration-gray-600" data-testid="raw-text">
            {line.text_raw}
          </div>
        )}
        <div className="flex items-start gap-2">
          <textarea
            data-testid="line-text"
            className="flex-1 min-w-0 bg-background border border-border rounded px-2 py-1 text-sm resize-y min-h-[2.2rem]"
            rows={Math.min(4, Math.ceil(text.length / 70) || 1)}
            value={text}
            disabled={disabled}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => text.trim() && text !== line.text && patch.mutate({ text })}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                (e.target as HTMLTextAreaElement).blur();
              } else if (e.key === "Escape") setText(line.text);
            }}
          />
          {line.edited_by !== "none" && (
            <Button title="Về bản gốc" disabled={disabled || revert.isPending} onClick={() => revert.mutate()}>
              <RotateCcw className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
        {line.edit_note && Boolean(line.edit_note.trim()) && (
          <div className="text-[11px] text-amber-300/80" data-testid="line-edit-note">
            AI ghi chú: {line.edit_note}
          </div>
        )}
        <ErrorBox error={patch.error || revert.error} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
function ManualPanel({
  cid,
  stage,
  setStage,
  units,
  hasScript,
  onStart,
  starting,
  onDone,
}: {
  cid: string;
  stage: Stage;
  setStage: (s: Stage) => void;
  units: UnitInfo[];
  hasScript: boolean;
  onStart: (s: Stage) => void;
  starting: boolean;
  onDone: () => void;
}) {
  const manualUnits = units.filter((u) => u.mode === "manual");
  return (
    <div className="rounded-xl border border-border bg-surface p-4 text-sm space-y-3" data-testid="manual-panel">
      <div className="flex flex-wrap items-center gap-2">
        <b className="text-gray-100">Chế độ thủ công</b>
        <span className="text-gray-400">bước:</span>
        {(["read", "dialogue"] as Stage[]).map((s) => (
          <button
            key={s}
            disabled={s === "dialogue" && !hasScript}
            onClick={() => setStage(s)}
            className={`px-2 py-0.5 rounded ${stage === s ? "bg-primary text-white" : "bg-surface-raised text-gray-300"} disabled:opacity-40`}
          >
            {s === "read" ? "1. Đọc truyện" : "2. Biên tập thoại"}
          </button>
        ))}
        <Button className="ml-auto" disabled={starting} onClick={() => onStart(stage)} data-testid="manual-prepare">
          Tạo gói {manualUnits.length ? "lại" : ""}
        </Button>
      </div>
      <ol className="text-xs text-gray-400 list-decimal pl-5 space-y-0.5">
        <li>Bấm “Tạo gói”, rồi tải từng gói (.zip) về và giải nén.</li>
        <li>Mở gemini.google.com, đính kèm ảnh trong thư mục images/ (nếu có) theo thứ tự tên file.</li>
        <li>Dán toàn bộ prompt.txt vào ô chat, gửi, rồi copy câu trả lời JSON dán vào ô dưới.</li>
      </ol>
      {manualUnits.length === 0 ? (
        <div className="text-gray-500 text-xs">Chưa tạo gói cho bước này.</div>
      ) : (
        <div className="space-y-3">
          <AutoPaste cid={cid} stage={stage} onDone={onDone} />
          <div className="space-y-2">
            {manualUnits.map((u) => (
              <PasteUnit key={`${stage}-${u.unit_index}`} cid={cid} stage={stage} unit={u} total={manualUnits.length} onDone={onDone} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AutoPaste({ cid, stage, onDone }: { cid: string; stage: Stage; onDone: () => void }) {
  const [raw, setRaw] = useState("");
  const [infoMsg, setInfoMsg] = useState<string | null>(null);
  const paste = useMutation({
    mutationFn: () => dialogueApi.paste(cid, stage, null, raw),
    onSuccess: (res: { message_vi?: string }) => {
      setRaw("");
      setInfoMsg(res?.message_vi || "Đã áp dụng kết quả thành công");
      onDone();
    },
  });

  return (
    <div className="rounded-lg border-2 border-dashed border-primary/40 bg-primary/5 p-3" data-testid="auto-paste-box">
      <div className="flex items-center justify-between text-xs font-semibold text-primary">
        <span className="flex items-center gap-1.5">
          <ClipboardPaste className="w-4 h-4" /> Dán kết quả (tự nhận gói)
        </span>
        <span className="text-[11px] font-normal text-gray-400">
          Tự động tìm gói có khung / câu khớp trong JSON
        </span>
      </div>
      <div className="mt-2 flex gap-2 items-start">
        <textarea
          className="flex-1 bg-background border border-border rounded px-2 py-1 font-mono text-xs h-20"
          placeholder="Dán JSON của bất kỳ gói nào vào đây — hệ thống sẽ tự tìm đúng gói…"
          value={raw}
          onChange={(e) => {
            setRaw(e.target.value);
            setInfoMsg(null);
          }}
          data-testid="auto-paste-text"
        />
        <Button
          variant="primary"
          disabled={!raw.trim() || paste.isPending}
          onClick={() => paste.mutate()}
          data-testid="auto-paste-btn"
        >
          <ClipboardPaste className="w-4 h-4" /> {paste.isPending ? "Đang xử lý…" : "Dán kết quả"}
        </Button>
      </div>
      {infoMsg && <p className="text-xs text-emerald-400 mt-1 font-medium">{infoMsg}</p>}
      {paste.error && (
        <div className="mt-1">
          <ErrorBox error={paste.error} />
          <pre className="text-[11px] text-red-300/80 whitespace-pre-wrap max-h-40 overflow-auto mt-1">
            {String((paste.error as { details?: { error?: string } }).details?.error ?? "")}
          </pre>
        </div>
      )}
    </div>
  );
}

function PasteUnit({
  cid,
  stage,
  unit,
  total,
  onDone,
}: {
  cid: string;
  stage: Stage;
  unit: UnitInfo;
  total: number;
  onDone: () => void;
}) {
  const [raw, setRaw] = useState("");
  const [infoMsg, setInfoMsg] = useState<string | null>(null);
  const paste = useMutation({
    mutationFn: () => dialogueApi.paste(cid, stage, unit.unit_index, raw),
    onSuccess: (res: { message_vi?: string }) => {
      setRaw("");
      if (res?.message_vi) {
        setInfoMsg(res.message_vi);
      }
      onDone();
    },
  });
  const done = unit.status === "succeeded";
  return (
    <div className="rounded-lg border border-border p-2.5" data-testid="paste-unit">
      <div className="flex items-center gap-2 text-xs">
        <b>
          Gói {unit.unit_index + 1}/{total}
        </b>
        {unit.size ? <span className="text-gray-500">({unit.size} {stage === "read" ? "khung" : "câu"})</span> : null}
        {done ? (
          <span className="text-emerald-300">✓ đã nhận</span>
        ) : (
          <span className="text-amber-300">chờ dán kết quả</span>
        )}
        <a className="ml-auto text-primary inline-flex items-center gap-1" href={dialogueApi.bundleUrl(cid, stage, unit.unit_index)}>
          <Download className="w-3.5 h-3.5" /> Tải gói
        </a>
      </div>
      {!done && (
        <div className="mt-2 flex gap-2 items-start">
          <textarea
            className="flex-1 bg-background border border-border rounded px-2 py-1 font-mono text-xs h-20"
            placeholder="Dán JSON Gemini trả về…"
            value={raw}
            onChange={(e) => {
              setRaw(e.target.value);
              setInfoMsg(null);
            }}
            data-testid="paste-text"
          />
          <Button variant="primary" disabled={!raw.trim() || paste.isPending} onClick={() => paste.mutate()}>
            <ClipboardPaste className="w-4 h-4" /> Dán kết quả
          </Button>
        </div>
      )}
      {infoMsg && <p className="text-xs text-emerald-400 mt-1 font-medium">{infoMsg}</p>}
      {paste.error && (
        <div className="mt-1">
          <ErrorBox error={paste.error} />
          <pre className="text-[11px] text-red-300/80 whitespace-pre-wrap max-h-40 overflow-auto mt-1">
            {String((paste.error as { details?: { error?: string } }).details?.error ?? "")}
          </pre>
        </div>
      )}
      {!paste.error && unit.error && !done && (
        <pre className="text-[11px] text-red-300/80 whitespace-pre-wrap max-h-24 overflow-auto mt-1">{unit.error}</pre>
      )}
    </div>
  );
}

