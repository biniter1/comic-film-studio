import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clapperboard,
  Copy,
  Film,
  Image as ImageIcon,
  Pencil,
  RotateCcw,
  Sparkles,
  TriangleAlert,
  User,
} from "lucide-react";
import {
  ANGLES,
  Beat,
  MOVE_VI,
  MOVEMENTS,
  SHOT_SIZES,
  SIZE_VI,
  SPEEDS,
  Shot,
  ShotPatch,
  ShotsData,
  shotsApi,
} from "../api/shots";
import { rememberChapter, studio } from "../api/studio";
import { useJob } from "../api/useJob";
import { Button, Empty, ErrorBox, JobProgress, PageHeader, StatusBadge } from "../components/common";

const TERMINAL = ["succeeded", "failed", "cancelled"];
const TRANSITION: Record<string, { label: string; cls: string }> = {
  cut: { label: "Cắt cảnh", cls: "bg-sky-900/60 text-sky-200" },
  continuous: { label: "Nối tiếp ⇢", cls: "bg-violet-900/60 text-violet-200" },
  match: { label: "Khớp hình", cls: "bg-teal-900/60 text-teal-200" },
};
const FACING_ICON: Record<string, string> = { left: "←", right: "→", camera: "●", away: "○" };
const POS_VI: Record<string, string> = { left: "Trái", center: "Giữa", right: "Phải" };
const DEPTH_VI: Record<string, string> = { fg: "gần", mg: "giữa", bg: "xa" };

export function ShotBoardPage() {
  const { cid = "" } = useParams();
  const qc = useQueryClient();
  useEffect(() => rememberChapter(cid), [cid]);
  const chapter = useQuery({ queryKey: ["chapter", cid], queryFn: () => studio.getChapter(cid) });
  const data = useQuery({ queryKey: ["shots", cid], queryFn: () => shotsApi.get(cid) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["shots", cid] });
    qc.invalidateQueries({ queryKey: ["chapter", cid] });
  };

  const [jobIds, setJobIds] = useState<string[]>([]);
  const plan = useMutation({
    mutationFn: (force: boolean) => shotsApi.plan(cid, force),
    onSuccess: (r) => setJobIds(r.jobs.map((j) => j.id)),
  });
  const approve = useMutation({ mutationFn: () => shotsApi.approve(cid), onSuccess: refresh });
  const ids = jobIds.length ? jobIds : data.data?.busy_job_id ? [data.data.busy_job_id] : [];
  const j0 = useJob(ids[0]);
  const j1 = useJob(ids[1]);
  const jobs = [j0.data, j1.data].filter(Boolean);
  const busy = jobs.some((j) => j && !TERMINAL.includes(j.status) && !(j.status === "queued" && j.user_action_required));
  const jobKey = jobs.map((j) => j?.status).join(",");
  useEffect(() => {
    if (jobKey) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobKey]);

  const d = data.data;
  const status = d?.status ?? chapter.data?.status;
  const plannable = ["dialogue_approved", "shots_draft", "plan_approved"].includes(status ?? "");
  const hasShots = (d?.shots.length ?? 0) > 0;
  const notes = d?.shots.reduce((n, s) => n + s.rule_notes.length, 0) ?? 0;
  const totalS = d?.shots.reduce((n, s) => n + s.duration_s, 0) ?? 0;
  const ch = chapter.data;

  return (
    <div className="p-8">
      <PageHeader
        title={ch ? `Bảng shot · ${ch.title}` : "Bảng shot"}
        subtitle={
          ch && (
            <span className="flex flex-wrap items-center gap-3">
              <Link to={`/chapters/${cid}/dialogue`} className="hover:text-gray-200">
                ← Kịch bản thoại
              </Link>
              {status && <StatusBadge status={status as never} />}
              {d && hasShots && (
                <span data-testid="shot-stats">
                  {d.scenes.length} scene · {d.shots.length} shot · {Math.round(totalS)}s
                  {notes > 0 && <span className="text-amber-300"> · {notes} cảnh báo</span>}
                </span>
              )}
              {d && (
                <Link to={`/projects/${d.project_id}/glossary`} className="text-primary hover:underline">
                  Nhân vật & bối cảnh
                </Link>
              )}
            </span>
          )
        }
        actions={
          <>
            <Button
              variant="primary"
              disabled={!plannable || busy || plan.isPending}
              onClick={() => plan.mutate(false)}
              data-testid="plan-btn"
              title="Chia scene rồi dựng storyboard từng shot. Scene đã làm sẽ được bỏ qua (không tốn credit)."
            >
              <Sparkles className="w-4 h-4" /> {hasShots ? "Chạy tiếp" : "Lập kế hoạch shot (AI)"}
            </Button>
            {hasShots && (
              <Button
                disabled={busy || plan.isPending}
                onClick={() =>
                  window.confirm("Lập lại toàn bộ scene và shot sẽ gọi AI lại cho cả chapter (tốn credit). Tiếp tục?") &&
                  plan.mutate(true)
                }
              >
                <RotateCcw className="w-4 h-4" /> Lập lại toàn bộ
              </Button>
            )}
            {hasShots && (
              <Button
                variant="primary"
                className="!bg-emerald-700 hover:!bg-emerald-600"
                disabled={busy || status === "plan_approved" || approve.isPending}
                onClick={() => approve.mutate()}
                data-testid="approve-plan"
              >
                <CheckCircle2 className="w-4 h-4" />
                {status === "plan_approved" ? "Đã duyệt kế hoạch" : "Duyệt kế hoạch shot"}
              </Button>
            )}
          </>
        }
      />
      <div className="space-y-3 mb-4 max-w-4xl">
        <ErrorBox error={data.error || plan.error || approve.error} />
        {jobs.map(
          (j) =>
            j && <JobProgress key={j.id} job={j} label={j.type === "analysis_plan" ? "Chia scene" : "Dựng storyboard từng scene"} />
        )}
        {!plannable && status && (
          <div className="text-sm text-amber-300">
            Hãy{" "}
            <Link to={`/chapters/${cid}/dialogue`} className="underline">
              duyệt kịch bản thoại
            </Link>{" "}
            trước khi lập kế hoạch shot.
          </div>
        )}
      </div>

      {data.isLoading ? (
        <div className="text-sm text-gray-400">Đang tải…</div>
      ) : !d || !hasShots ? (
        <Empty icon={<Clapperboard className="w-6 h-6" />} title="Chưa có shot nào">
          {plannable ? "Bấm “Lập kế hoạch shot (AI)” để chia scene và dựng storyboard." : "Duyệt kịch bản thoại trước."}
        </Empty>
      ) : (
        <div className="space-y-8">
          {d.scenes.map((sc) => {
            const shots = d.shots.filter((s) => s.scene_id === sc.id);
            const loc = d.locations.find((l) => l.key === sc.location_key);
            return (
              <section key={sc.id} data-testid="scene">
                <div className="flex flex-wrap items-baseline gap-3 mb-3">
                  <h2 className="text-lg font-semibold text-gray-100">{sc.code}</h2>
                  {loc && <span className="text-xs px-2 py-0.5 rounded bg-surface-raised text-gray-300">📍 {loc.name_vi}</span>}
                  {sc.mood && <span className="text-xs text-gray-400">{sc.mood}</span>}
                  <span className="text-sm text-gray-400">{sc.summary}</span>
                </div>
                <div className="grid gap-4 xl:grid-cols-2">
                  {shots.map((s) => (
                    <ShotCard key={s.id} shot={s} data={d} disabled={busy} onChanged={refresh} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
function ShotCard({ shot, data, disabled, onChanged }: { shot: Shot; data: ShotsData; disabled: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const frames = useMemo(() => new Map(data.frames.map((f) => [f.id, f])), [data.frames]);
  const name = (key: string) => data.characters.find((c) => c.key === key)?.name ?? key;
  const tr = TRANSITION[shot.transition_in];
  return (
    <div className="rounded-xl border border-border bg-surface p-3 space-y-2" data-testid="shot-card">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono font-semibold text-gray-100 text-sm">{shot.code}</span>
        <span className={`px-1.5 py-0.5 rounded ${tr.cls}`}>{tr.label}</span>
        <span className="text-gray-500 font-mono">
          {shot.chain_code}·{shot.chain_pos}
        </span>
        <span className="text-gray-300">{shot.duration_s.toFixed(1)}s</span>
        {shot.inserted && <span className="px-1.5 py-0.5 rounded bg-pink-900/60 text-pink-200">Shot chèn thêm</span>}
        {shot.edited_by === "user" && <span className="px-1.5 py-0.5 rounded bg-sky-900/60 text-sky-200">bạn sửa</span>}
        <button className="ml-auto text-gray-400 hover:text-gray-100" onClick={() => setEditing((v) => !v)} disabled={disabled} data-testid="edit-shot">
          <Pencil className="w-4 h-4" />
        </button>
      </div>

      <div className="flex gap-3">
        <div className="flex gap-1 shrink-0">
          {shot.frame_ids.length ? (
            shot.frame_ids.slice(0, 2).map((fid) => (
              <img key={fid} src={frames.get(fid)?.image_url} alt="" className="w-24 h-32 object-cover object-top rounded border border-border" loading="lazy" />
            ))
          ) : (
            <div className="w-24 h-32 rounded border border-dashed border-border flex items-center justify-center text-[11px] text-gray-500 text-center p-1">
              không có khung gốc
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0 space-y-1.5 text-xs">
          <div className="flex flex-wrap gap-1.5" data-testid="camera-chips">
            <Chip>🎥 {SIZE_VI[shot.camera.shot_size] ?? shot.camera.shot_size}</Chip>
            <Chip>
              {MOVE_VI[shot.camera.movement] ?? shot.camera.movement} · {shot.camera.speed}
            </Chip>
            <Chip>góc {shot.camera.angle}</Chip>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {shot.blocking.map((b, i) => (
              <span key={i} className="px-1.5 py-0.5 rounded bg-surface-raised text-gray-200" title={b.pose}>
                <User className="inline w-3 h-3 mr-0.5" />
                {name(b.character_key)} · {POS_VI[b.screen_pos]} {DEPTH_VI[b.depth]} {FACING_ICON[b.facing]}
              </span>
            ))}
          </div>
          <BeatBar beats={shot.beats} duration={shot.duration_s} />
          {shot.start_state && (
            <div className="text-gray-400">
              <ArrowRight className="inline w-3 h-3" /> Bắt đầu: <span className="text-gray-300">{shot.start_state}</span>
            </div>
          )}
          {shot.end_state && (
            <div className="text-gray-400">
              <ArrowLeft className="inline w-3 h-3 rotate-180" /> Kết thúc: <span className="text-gray-300">{shot.end_state}</span>
            </div>
          )}
        </div>
      </div>

      {(shot.lines.length > 0 || shot.titles.length > 0) && (
        <div className="rounded bg-background/60 p-2 text-xs space-y-0.5">
          {shot.lines
            .filter((l) => !["technique_name", "sfx", "system"].includes(l.kind))
            .map((l) => (
              <div key={l.id}>
                <span className="text-gray-500">{l.speaker ?? "Dẫn truyện"}: </span>
                <span className="text-gray-200">{l.text}</span>
              </div>
            ))}
          {shot.titles.map((t, i) => (
            <div key={i} className={t.style === "technique" ? "text-fuchsia-300 font-semibold" : "text-gray-400"}>
              {t.style === "technique" ? "✦ " : t.style === "sfx" ? "♪ " : "▣ "}
              {t.text}
            </div>
          ))}
        </div>
      )}

      {shot.rule_notes.length > 0 && (
        <ul className="text-[11px] text-amber-300 space-y-0.5" data-testid="rule-notes">
          {shot.rule_notes.map((n, i) => (
            <li key={i}>
              <TriangleAlert className="inline w-3 h-3 mr-1" />
              {n}
            </li>
          ))}
        </ul>
      )}

      <PromptBlock
        title="Prompt keyframe (Nano Banana)"
        icon={<ImageIcon className="w-3.5 h-3.5" />}
        text={shot.keyframe_prompt}
        overridden={!!shot.prompt_override?.keyframe}
        attachments={shot.attachments}
      />
      <PromptBlock
        title="Prompt video (Muse)"
        icon={<Film className="w-3.5 h-3.5" />}
        text={shot.video_prompt}
        overridden={!!shot.prompt_override?.video}
      />

      {editing && <ShotEditor shot={shot} onDone={() => { setEditing(false); onChanged(); }} />}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="px-1.5 py-0.5 rounded bg-indigo-950/70 text-indigo-200">{children}</span>;
}

const BEAT_COLORS = ["bg-indigo-600/70", "bg-violet-600/70", "bg-fuchsia-600/70", "bg-pink-600/70", "bg-rose-600/70"];

function BeatBar({ beats, duration }: { beats: Beat[]; duration: number }) {
  return (
    <div data-testid="beat-bar">
      <div className="flex h-2 rounded overflow-hidden bg-surface-raised">
        {beats.map((b, i) => (
          <div key={i} className={BEAT_COLORS[i % BEAT_COLORS.length]} style={{ width: `${((b.t1 - b.t0) / duration) * 100}%` }} />
        ))}
      </div>
      <ol className="mt-1 space-y-0.5 text-gray-300">
        {beats.map((b, i) => (
          <li key={i}>
            <span className="font-mono text-gray-500">
              {b.t0.toFixed(1)}–{b.t1.toFixed(1)}s
            </span>{" "}
            {b.action}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PromptBlock({
  title,
  icon,
  text,
  overridden,
  attachments,
}: {
  title: string;
  icon: React.ReactNode;
  text: string;
  overridden: boolean;
  attachments?: Shot["attachments"];
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className="rounded border border-border">
      <div className="flex items-center gap-2 px-2 py-1 text-xs">
        <button className="flex items-center gap-1.5 text-gray-300 hover:text-white" onClick={() => setOpen((v) => !v)}>
          {icon} {title} {overridden && <span className="text-sky-300">(sửa tay)</span>}
        </button>
        <span className="text-gray-500">{text.split(/\s+/).length} từ</span>
        <button className="ml-auto flex items-center gap-1 text-primary" onClick={copy} data-testid="copy-prompt">
          <Copy className="w-3.5 h-3.5" /> {copied ? "Đã copy" : "Copy"}
        </button>
      </div>
      {open && (
        <div className="border-t border-border p-2 space-y-2">
          {attachments && attachments.length > 0 && (
            <div className="flex gap-2">
              {attachments.map((a, i) => (
                <a key={i} href={a.url} target="_blank" rel="noreferrer" className="text-center" title={a.label}>
                  <img src={a.url} alt="" className="w-14 h-14 object-cover rounded border border-border" />
                  <div className="text-[10px] text-gray-400">Ảnh {i + 1}</div>
                </a>
              ))}
            </div>
          )}
          <pre className="whitespace-pre-wrap text-[11px] text-gray-300 font-mono" data-testid="prompt-text">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
function ShotEditor({ shot, onDone }: { shot: Shot; onDone: () => void }) {
  const [form, setForm] = useState({
    transition_in: shot.transition_in,
    duration_s: shot.duration_s,
    camera: { ...shot.camera },
    start_state: shot.start_state,
    end_state: shot.end_state,
    beats: shot.beats.map((b) => ({ ...b })),
    keyframe: shot.prompt_override?.keyframe ?? "",
    video: shot.prompt_override?.video ?? "",
  });
  const save = useMutation({
    mutationFn: () => {
      const patch: ShotPatch = {
        transition_in: form.transition_in,
        duration_s: Number(form.duration_s),
        camera: form.camera,
        start_state: form.start_state,
        end_state: form.end_state,
        beats: form.beats.filter((b) => b.action.trim()),
        prompt_override: { keyframe: form.keyframe || null, video: form.video || null },
      };
      return shotsApi.patch(shot.id, patch);
    },
    onSuccess: onDone,
  });
  const sel = "bg-background border border-border rounded px-1.5 py-1 text-xs";
  const cam = (k: keyof typeof form.camera, opts: string[], labels?: Record<string, string>) => (
    <select className={sel} value={form.camera[k]} onChange={(e) => setForm({ ...form, camera: { ...form.camera, [k]: e.target.value } })}>
      {opts.map((o) => (
        <option key={o} value={o}>
          {labels?.[o] ?? o}
        </option>
      ))}
    </select>
  );
  return (
    <div className="rounded-lg border border-primary/50 bg-background/60 p-3 space-y-2 text-xs" data-testid="shot-editor">
      <div className="flex flex-wrap gap-2 items-center">
        <select className={sel} value={form.transition_in} onChange={(e) => setForm({ ...form, transition_in: e.target.value as Shot["transition_in"] })}>
          <option value="cut">Cắt cảnh</option>
          <option value="continuous">Nối tiếp</option>
          <option value="match">Khớp hình</option>
        </select>
        <label className="flex items-center gap-1">
          <input type="number" step="0.5" min="1" max="15" className={`${sel} w-16`} value={form.duration_s} onChange={(e) => setForm({ ...form, duration_s: Number(e.target.value) })} />s
        </label>
        {cam("shot_size", SHOT_SIZES, SIZE_VI)}
        {cam("movement", MOVEMENTS, MOVE_VI)}
        {cam("speed", SPEEDS)}
        {cam("angle", ANGLES)}
      </div>
      <input className={`${sel} w-full`} placeholder="Bắt đầu (start_state)" value={form.start_state} onChange={(e) => setForm({ ...form, start_state: e.target.value })} />
      <input className={`${sel} w-full`} placeholder="Kết thúc (end_state)" value={form.end_state} onChange={(e) => setForm({ ...form, end_state: e.target.value })} />
      <div className="space-y-1">
        {form.beats.map((b, i) => (
          <div key={i} className="flex gap-1 items-center">
            <span className="font-mono text-gray-500 w-20">
              {b.t0.toFixed(1)}–{b.t1.toFixed(1)}s
            </span>
            <input
              className={`${sel} flex-1`}
              value={b.action}
              onChange={(e) => setForm({ ...form, beats: form.beats.map((x, k) => (k === i ? { ...x, action: e.target.value } : x)) })}
            />
          </div>
        ))}
        <button
          className="text-primary"
          onClick={() =>
            setForm({
              ...form,
              beats: [...form.beats, { t0: form.beats.at(-1)?.t1 ?? 0, t1: Number(form.duration_s), action: "" }],
            })
          }
        >
          + Thêm nhịp
        </button>
      </div>
      <textarea className={`${sel} w-full h-16 font-mono`} placeholder="Prompt keyframe tự viết (để trống = app tự ghép)" value={form.keyframe} onChange={(e) => setForm({ ...form, keyframe: e.target.value })} />
      <textarea className={`${sel} w-full h-12 font-mono`} placeholder="Prompt video tự viết (để trống = app tự ghép)" value={form.video} onChange={(e) => setForm({ ...form, video: e.target.value })} />
      <ErrorBox error={save.error} />
      <div className="flex gap-2">
        <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()} data-testid="save-shot">
          Lưu
        </Button>
        <Button onClick={onDone}>Hủy</Button>
      </div>
    </div>
  );
}
