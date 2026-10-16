import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Download,
  Plus,
  Star,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  AGE_LABEL,
  AddressRule,
  AgeGroup,
  Character,
  CharacterOutfit,
  GENDER_LABEL,
  Gender,
  GlossaryTerm,
  HEIGHT_CLASS_LABEL,
  HeightClass,
  LocationItem,
  ReviewStatus,
  SHEET_STATUS_LABEL,
  SheetStatus,
  TERM_KIND_LABEL,
  dialogueApi,
} from "../api/dialogue";
import { FrameItem, studio } from "../api/studio";
import { Button, ErrorBox, PageHeader } from "../components/common";

type Tab = "terms" | "address" | "characters" | "locations";
const TABS: { id: Tab; label: string }[] = [
  { id: "terms", label: "Thuật ngữ" },
  { id: "address", label: "Xưng hô" },
  { id: "characters", label: "Nhân vật" },
  { id: "locations", label: "Bối cảnh" },
];

const input = "bg-background border border-border rounded px-2 py-1 text-sm";

export function GlossaryPage() {
  const { pid = "" } = useParams();
  const [tab, setTab] = useState<Tab>("terms");
  const project = useQuery({ queryKey: ["project", pid], queryFn: () => studio.getProject(pid) });

  return (
    <div className="p-8 max-w-6xl">
      <PageHeader
        title={`Thuật ngữ & Hồ sơ · ${project.data?.name ?? "…"}`}
        subtitle={
          <span>
            <Link to={`/projects/${pid}`} className="hover:text-gray-200">
              ← Dự án
            </Link>{" "}
            · Dùng chung cho mọi chapter của dự án. Khóa ngoại hình nhân vật & bối cảnh (lớp khóa 1).
          </span>
        }
      />
      <div className="flex gap-1 mb-4 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            data-testid={`tab-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm -mb-px border-b-2 ${
              tab === t.id ? "border-primary text-white" : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "terms" && <TermsTab pid={pid} />}
      {tab === "address" && <AddressTab pid={pid} />}
      {tab === "characters" && <CharactersTab pid={pid} />}
      {tab === "locations" && <LocationsTab pid={pid} />}
    </div>
  );
}

function StatusPill({ status }: { status: ReviewStatus }) {
  const cls = {
    suggested: "bg-amber-900/60 text-amber-200",
    approved: "bg-emerald-900/60 text-emerald-200",
    rejected: "bg-gray-700/60 text-gray-400",
  }[status];
  const label = { suggested: "AI đề xuất", approved: "Đã duyệt", rejected: "Đã bỏ" }[status];
  return <span className={`px-2 py-0.5 rounded-full text-[11px] ${cls}`}>{label}</span>;
}

function ReviewButtons({
  status,
  onSet,
  disabled,
}: {
  status: ReviewStatus;
  onSet: (s: ReviewStatus) => void;
  disabled?: boolean;
}) {
  return (
    <>
      {status !== "approved" && (
        <Button title="Duyệt" disabled={disabled} onClick={() => onSet("approved")} data-testid="approve-item">
          <Check className="w-3.5 h-3.5" />
        </Button>
      )}
      {status !== "rejected" && (
        <Button title="Bỏ đề xuất" disabled={disabled} onClick={() => onSet("rejected")}>
          <X className="w-3.5 h-3.5" />
        </Button>
      )}
    </>
  );
}

const splitList = (s: string) =>
  s
    .split(/[,;\n]/)
    .map((x) => x.trim())
    .filter(Boolean);

function countWords(str: string | null | undefined): number {
  if (!str) return 0;
  const trimmed = str.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).length;
}

/** Text that saves on blur / Enter. */
function InlineText({
  value,
  onSave,
  className = "",
  placeholder,
}: {
  value: string;
  onSave: (v: string) => void;
  className?: string;
  placeholder?: string;
}) {
  const [v, setV] = useState(value);
  const [base, setBase] = useState(value);
  if (base !== value) {
    setBase(value);
    setV(value);
  }
  return (
    <input
      className={`${input} ${className}`}
      value={v}
      placeholder={placeholder}
      onChange={(e) => setV(e.target.value)}
      onBlur={() => v !== value && onSave(v)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setV(value);
      }}
    />
  );
}

// ---------------------------------------------------------------------------------------
// Terms tab
// ---------------------------------------------------------------------------------------
function TermsTab({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const key = ["glossary", pid];
  const q = useQuery({ queryKey: key, queryFn: () => dialogueApi.glossary(pid) });
  const done = () => qc.invalidateQueries({ queryKey: key });
  const update = useMutation({
    mutationFn: ({ id, p }: { id: string; p: Partial<GlossaryTerm> }) => dialogueApi.updateTerm(id, p),
    onSuccess: done,
  });
  const del = useMutation({ mutationFn: (id: string) => dialogueApi.deleteTerm(id), onSuccess: done });
  const merge = useMutation({
    mutationFn: ({ id, into }: { id: string; into: string }) => dialogueApi.mergeTerm(id, into),
    onSuccess: done,
  });
  const [form, setForm] = useState({ term: "", kind: "other", variants: "" });
  const create = useMutation({
    mutationFn: () =>
      dialogueApi.createTerm(pid, { term: form.term.trim(), kind: form.kind, variants: splitList(form.variants) }),
    onSuccess: () => {
      setForm({ term: "", kind: "other", variants: "" });
      done();
    },
  });
  const terms = q.data ?? [];
  return (
    <div className="space-y-3">
      <ErrorBox error={q.error || update.error || del.error || merge.error || create.error} />
      <form
        className="flex flex-wrap gap-2 items-center rounded-xl border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (form.term.trim()) create.mutate();
        }}
      >
        <input
          className={`${input} w-56`}
          placeholder="Thuật ngữ chuẩn (vd: Lâm Phong)"
          value={form.term}
          onChange={(e) => setForm({ ...form, term: e.target.value })}
          data-testid="new-term"
        />
        <select className={input} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          {Object.entries(TERM_KIND_LABEL).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <input
          className={`${input} flex-1 min-w-[16rem]`}
          placeholder="Cách viết sai hay gặp, cách nhau bằng dấu phẩy (vd: Lam Phong, Lâm phong)"
          value={form.variants}
          onChange={(e) => setForm({ ...form, variants: e.target.value })}
        />
        <Button variant="primary" type="submit" disabled={!form.term.trim() || create.isPending}>
          <Plus className="w-4 h-4" /> Thêm
        </Button>
      </form>
      <div className="rounded-xl border border-border bg-surface divide-y divide-border">
        {terms.length === 0 && <div className="p-4 text-sm text-gray-400">Chưa có thuật ngữ nào.</div>}
        {terms.map((t) => (
          <div key={t.id} className="flex flex-wrap items-center gap-2 px-3 py-2" data-testid="term-row">
            <InlineText value={t.term} className="w-48 font-medium" onSave={(v) => v.trim() && update.mutate({ id: t.id, p: { term: v } })} />
            <select
              className={input}
              value={t.kind}
              onChange={(e) => update.mutate({ id: t.id, p: { kind: e.target.value } })}
            >
              {Object.entries(TERM_KIND_LABEL).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <InlineText
              value={t.variants.join(", ")}
              className="flex-1 min-w-[12rem] text-gray-300"
              placeholder="biến thể sai…"
              onSave={(v) => update.mutate({ id: t.id, p: { variants: splitList(v) } })}
            />
            <StatusPill status={t.status} />
            <ReviewButtons status={t.status} onSet={(s) => update.mutate({ id: t.id, p: { status: s } })} />
            <select
              className={`${input} w-32`}
              value=""
              title="Gộp: thuật ngữ này là cách viết sai của thuật ngữ khác"
              onChange={(e) => e.target.value && merge.mutate({ id: t.id, into: e.target.value })}
            >
              <option value="">⇢ Gộp vào…</option>
              {terms
                .filter((o) => o.id !== t.id && o.status !== "rejected")
                .map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.term}
                  </option>
                ))}
            </select>
            <Button variant="danger" title="Xóa" onClick={() => window.confirm(`Xóa "${t.term}"?`) && del.mutate(t.id)}>
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
            {t.note && <div className="basis-full text-xs text-gray-500 pl-1">{t.note}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Address tab
// ---------------------------------------------------------------------------------------
function AddressTab({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const key = ["address-rules", pid];
  const q = useQuery({ queryKey: key, queryFn: () => dialogueApi.rules(pid) });
  const chars = useQuery({ queryKey: ["characters", pid], queryFn: () => dialogueApi.characters(pid) });
  const done = () => qc.invalidateQueries({ queryKey: key });
  const update = useMutation({
    mutationFn: ({ id, p }: { id: string; p: Partial<AddressRule> }) => dialogueApi.updateRule(id, p),
    onSuccess: done,
  });
  const del = useMutation({ mutationFn: (id: string) => dialogueApi.deleteRule(id), onSuccess: done });
  const [form, setForm] = useState({ speaker_key: "", listener_key: "", self_term: "", address_term: "" });
  const create = useMutation({
    mutationFn: () => dialogueApi.createRule(pid, form),
    onSuccess: () => {
      setForm({ speaker_key: "", listener_key: "", self_term: "", address_term: "" });
      done();
    },
  });
  const charMap = new Map((chars.data ?? []).map((c) => [c.key, c.name]));
  const name = (k: string) => charMap.get(k) ?? k;
  const valid = form.speaker_key && form.listener_key && form.self_term.trim() && form.address_term.trim();
  return (
    <div className="space-y-3">
      <ErrorBox error={q.error || update.error || del.error || create.error} />
      <form
        className="flex flex-wrap gap-2 items-center rounded-xl border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) create.mutate();
        }}
      >
        <select
          className={input}
          value={form.speaker_key}
          onChange={(e) => setForm({ ...form, speaker_key: e.target.value })}
        >
          <option value="">Người nói…</option>
          {(chars.data ?? []).map((c) => (
            <option key={c.key} value={c.key}>
              {c.name}
            </option>
          ))}
        </select>
        <span className="text-gray-500">→</span>
        <select
          className={input}
          value={form.listener_key}
          onChange={(e) => setForm({ ...form, listener_key: e.target.value })}
        >
          <option value="">Người nghe…</option>
          {(chars.data ?? []).map((c) => (
            <option key={c.key} value={c.key}>
              {c.name}
            </option>
          ))}
        </select>
        <input
          className={`${input} w-28`}
          placeholder="tự xưng (ta)"
          value={form.self_term}
          onChange={(e) => setForm({ ...form, self_term: e.target.value })}
        />
        <input
          className={`${input} w-28`}
          placeholder="gọi là (ngươi)"
          value={form.address_term}
          onChange={(e) => setForm({ ...form, address_term: e.target.value })}
        />
        <Button variant="primary" type="submit" disabled={!valid || create.isPending}>
          <Plus className="w-4 h-4" /> Thêm
        </Button>
      </form>
      <div className="rounded-xl border border-border bg-surface divide-y divide-border">
        {(q.data ?? []).length === 0 && <div className="p-4 text-sm text-gray-400">Chưa có quy tắc xưng hô.</div>}
        {(q.data ?? []).map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
            <span className="w-36 truncate font-medium">{name(r.speaker_key)}</span>
            <span className="text-gray-500">→</span>
            <span className="w-36 truncate">{name(r.listener_key)}</span>
            <span className="text-gray-500">xưng</span>
            <InlineText value={r.self_term} className="w-24" onSave={(v) => v.trim() && update.mutate({ id: r.id, p: { self_term: v } })} />
            <span className="text-gray-500">gọi</span>
            <InlineText value={r.address_term} className="w-24" onSave={(v) => v.trim() && update.mutate({ id: r.id, p: { address_term: v } })} />
            <StatusPill status={r.status} />
            <ReviewButtons status={r.status} onSet={(s) => update.mutate({ id: r.id, p: { status: s } })} />
            <Button variant="danger" title="Xóa" onClick={() => del.mutate(r.id)}>
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
            {r.note && <div className="basis-full text-xs text-gray-500">{r.note}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Reusable Sheet Block (Character Outfit Sheet & Location Sheet)
// ---------------------------------------------------------------------------------------
function SheetBlock({
  target,
  id,
  sheetStatus,
  sheetUrl,
  refFrameCount,
  onRefresh,
}: {
  target: "outfits" | "locations";
  id: string;
  sheetStatus: SheetStatus;
  sheetUrl: string | null;
  refFrameCount: number;
  onRefresh: () => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const uploadMut = useMutation({
    mutationFn: (file: File) => dialogueApi.uploadSheet(target, id, file),
    onSuccess: () => {
      setError(null);
      onRefresh();
    },
    onError: (err: unknown) => {
      const e = err as { message_vi?: string; message?: string };
      setError(e.message_vi || e.message || "Tải lên thất bại");
    },
  });

  const approveMut = useMutation({
    mutationFn: () => dialogueApi.approveSheet(target, id),
    onSuccess: onRefresh,
  });

  const rejectMut = useMutation({
    mutationFn: () => dialogueApi.rejectSheet(target, id),
    onSuccess: onRefresh,
  });

  const statusCls = {
    missing: "bg-gray-800 text-gray-400 border border-gray-700",
    pending: "bg-amber-950/70 text-amber-300 border border-amber-800",
    approved: "bg-emerald-950/70 text-emerald-300 border border-emerald-800",
  }[sheetStatus];

  return (
    <div className="mt-2 rounded-lg border border-border/80 bg-background/50 p-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-300">Bảng tham chiếu (Sheet):</span>
          <span
            data-testid="sheet-status"
            className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${statusCls}`}
          >
            {SHEET_STATUS_LABEL[sheetStatus]}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={refFrameCount > 0 ? dialogueApi.sheetBundleUrl(target, id) : undefined}
            download
            data-testid="sheet-bundle-btn"
            onClick={(e) => {
              if (refFrameCount === 0) {
                e.preventDefault();
                alert("Chọn 2–4 khung tham chiếu trước");
              }
            }}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded border transition-colors ${
              refFrameCount > 0
                ? "bg-surface hover:bg-surface/80 border-border text-gray-200"
                : "opacity-50 cursor-not-allowed border-border text-gray-400"
            }`}
            title={refFrameCount === 0 ? "Chọn 2–4 khung tham chiếu trước" : "Tải gói ảnh + prompt cho Gemini"}
          >
            <Download className="w-3.5 h-3.5" /> Tải gói
          </a>

          <label
            data-testid="sheet-drop-zone"
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              const file = e.dataTransfer.files?.[0];
              if (file) uploadMut.mutate(file);
            }}
            className={`cursor-pointer inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded border transition-colors ${
              isDragging
                ? "border-primary bg-primary/20 text-white"
                : "border-dashed border-border bg-surface hover:border-gray-400 text-gray-300"
            }`}
          >
            <Upload className="w-3.5 h-3.5" /> Thả ảnh sheet
            <input
              type="file"
              accept="image/*"
              data-testid="sheet-file-input"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadMut.mutate(file);
                e.target.value = "";
              }}
            />
          </label>

          {sheetUrl && (
            <>
              {sheetStatus !== "approved" && (
                <Button
                  variant="primary"
                  data-testid="sheet-approve-btn"
                  onClick={() => approveMut.mutate()}
                  disabled={approveMut.isPending}
                  className="text-xs py-1 px-2.5"
                >
                  <Check className="w-3.5 h-3.5" /> Duyệt
                </Button>
              )}
              <Button
                variant="secondary"
                data-testid="sheet-reject-btn"
                onClick={() => rejectMut.mutate()}
                disabled={rejectMut.isPending}
                className="text-xs py-1 px-2.5 text-red-400 hover:text-red-300"
              >
                <X className="w-3.5 h-3.5" /> Bỏ
              </Button>
            </>
          )}
        </div>
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}

      {sheetUrl ? (
        <div className="relative rounded overflow-hidden border border-border/80 bg-black/40 flex items-center justify-center p-1">
          <img
            src={sheetUrl}
            alt="Sheet preview"
            className="max-h-56 max-w-full object-contain rounded"
          />
        </div>
      ) : (
        <div className="text-xs text-gray-500 italic py-1">
          Chưa có ảnh sheet. Tải gói về dán vào Gemini, sau đó tải ảnh kết quả thả vào đây.
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Characters tab (Cards with Look Lock, Ref Frames & Outfits)
// ---------------------------------------------------------------------------------------
function CharactersTab({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const key = ["bible", pid];
  const q = useQuery({ queryKey: key, queryFn: () => dialogueApi.bible(pid) });
  const done = () => {
    qc.invalidateQueries({ queryKey: key });
    qc.invalidateQueries({ queryKey: ["characters", pid] });
  };

  const empty = {
    name: "",
    gender: "unknown" as Gender,
    age_group: "unknown" as AgeGroup,
    height_class: "average" as HeightClass,
  };
  const [form, setForm] = useState(empty);
  const create = useMutation({
    mutationFn: () =>
      dialogueApi.createCharacter(pid, {
        ...form,
        name: form.name.trim(),
      }),
    onSuccess: () => {
      setForm(empty);
      done();
    },
  });

  const chars = q.data?.characters ?? [];

  return (
    <div className="space-y-4">
      <ErrorBox error={q.error || create.error} />
      <form
        className="flex flex-wrap gap-2 items-center rounded-xl border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (form.name.trim()) create.mutate();
        }}
      >
        <input
          className={`${input} w-52`}
          placeholder="Tên nhân vật mới"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <GenderAge
          gender={form.gender}
          age={form.age_group}
          onChange={(p) => setForm({ ...form, ...p })}
        />
        <select
          className={input}
          value={form.height_class}
          onChange={(e) => setForm({ ...form, height_class: e.target.value as HeightClass })}
        >
          {Object.entries(HEIGHT_CLASS_LABEL).map(([val, label]) => (
            <option key={val} value={val}>
              Dáng: {label}
            </option>
          ))}
        </select>
        <Button variant="primary" type="submit" disabled={!form.name.trim() || create.isPending}>
          <Plus className="w-4 h-4" /> Thêm nhân vật
        </Button>
      </form>

      {chars.length === 0 && (
        <div className="p-8 text-center text-sm text-gray-400 bg-surface rounded-xl border border-border">
          Chưa có nhân vật nào. Hãy thêm nhân vật hoặc chạy phân tích chapter.
        </div>
      )}

      <div className="space-y-4">
        {chars.map((c) => (
          <CharacterCard key={c.id} c={c} allChars={chars} onUpdated={done} />
        ))}
      </div>
    </div>
  );
}

function CharacterCard({
  c,
  allChars,
  onUpdated,
}: {
  c: Character;
  allChars: Character[];
  onUpdated: () => void;
}) {
  const update = useMutation({
    mutationFn: (patch: Partial<Character>) => dialogueApi.updateCharacter(c.id, patch),
    onSuccess: onUpdated,
  });
  const del = useMutation({
    mutationFn: () => dialogueApi.deleteCharacter(c.id),
    onSuccess: onUpdated,
  });
  const merge = useMutation({
    mutationFn: (into: string) => dialogueApi.mergeCharacter(c.id, into),
    onSuccess: onUpdated,
  });

  // Outfits
  const createOutfit = useMutation({
    mutationFn: (data: Partial<CharacterOutfit>) => dialogueApi.createOutfit(c.id, data),
    onSuccess: onUpdated,
  });
  const updateOutfit = useMutation({
    mutationFn: ({ oid, patch }: { oid: string; patch: Partial<CharacterOutfit> }) =>
      dialogueApi.updateOutfit(oid, patch),
    onSuccess: onUpdated,
  });
  const delOutfit = useMutation({
    mutationFn: (oid: string) => dialogueApi.deleteOutfit(oid),
    onSuccess: onUpdated,
  });

  // Suggestions for ref frames
  const suggestions = useQuery({
    queryKey: ["frame-suggestions", c.id],
    queryFn: () => dialogueApi.frameSuggestions(c.id),
  });

  // Local state for look_lock
  const [lookLockText, setLookLockText] = useState(c.look_lock ?? "");
  const [newOutfitName, setNewOutfitName] = useState("");
  const [newOutfitLock, setNewOutfitLock] = useState("");
  const [newOutfitShortId, setNewOutfitShortId] = useState("");

  const words = countWords(lookLockText);
  const refIds = c.ref_frame_ids ?? [];

  const toggleRefFrame = (fid: string) => {
    const next = refIds.includes(fid) ? refIds.filter((id) => id !== fid) : [...refIds, fid];
    update.mutate({ ref_frame_ids: next });
  };

  const outfits = c.outfits ?? [];

  return (
    <div
      className="rounded-xl border border-border bg-surface p-4 space-y-4"
      data-testid="character-row"
    >
      <ErrorBox error={update.error || del.error || merge.error || createOutfit.error} />

      {/* Row 1: Basic info */}
      <div className="flex flex-wrap items-center gap-2">
        <InlineText
          value={c.name}
          className="w-44 font-semibold text-base"
          onSave={(v) => v.trim() && update.mutate({ name: v })}
        />
        <span className="font-mono text-xs text-gray-500 w-28 truncate" title="key">
          {c.key}
        </span>
        <GenderAge
          gender={c.gender}
          age={c.age_group}
          onChange={(p) => update.mutate(p)}
        />
        <select
          className={input}
          value={c.height_class || "average"}
          onChange={(e) => update.mutate({ height_class: e.target.value as HeightClass })}
        >
          {Object.entries(HEIGHT_CLASS_LABEL).map(([val, label]) => (
            <option key={val} value={val}>
              {label}
            </option>
          ))}
        </select>
        <InlineText
          value={(c.aliases ?? []).join(", ")}
          className="w-40"
          placeholder="bí danh…"
          onSave={(v) => update.mutate({ aliases: splitList(v) })}
        />
        <InlineText
          value={c.voice_style ?? ""}
          className="w-36"
          placeholder="kiểu giọng…"
          onSave={(v) => update.mutate({ voice_style: v })}
        />
        <span className="text-xs text-gray-400">{c.line_count ?? 0} câu</span>
        <StatusPill status={c.status} />
        <ReviewButtons status={c.status} onSet={(s) => update.mutate({ status: s })} />

        <select
          className={`${input} w-28 text-xs`}
          value=""
          title="Gộp nhân vật"
          onChange={(e) =>
            e.target.value &&
            window.confirm(`Gộp "${c.name}" vào nhân vật đã chọn?`) &&
            merge.mutate(e.target.value)
          }
        >
          <option value="">⇢ Gộp vào…</option>
          {allChars
            .filter((o) => o.id !== c.id)
            .map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
        </select>
        <Button
          variant="danger"
          title="Xóa nhân vật"
          onClick={() =>
            window.confirm(`Xóa "${c.name}"? Câu thoại giữ tên này dạng nhân vật phụ.`) &&
            del.mutate()
          }
        >
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* Row 2: Look lock & Look status */}
      <div className="rounded-lg border border-border/80 bg-background/40 p-3 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-200">
              Khóa ngoại hình (look_lock — EN, ≤60 từ, chỉ đặc điểm cố định, không quần áo):
            </span>
            <span
              className={`text-xs ${
                words > 60 ? "text-amber-400 font-bold" : "text-gray-400"
              }`}
            >
              {words}/60 từ {words > 60 && "⚠️ Vượt quá 60 từ"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {c.look_status === "approved" ? (
              <div className="flex items-center gap-1.5">
                <span className="px-2 py-0.5 rounded text-xs bg-emerald-950 text-emerald-300 border border-emerald-800">
                  Ngoại hình: Đã duyệt
                </span>
                <Button
                  variant="secondary"
                  className="text-xs py-0.5 px-2"
                  onClick={() => update.mutate({ look_status: "draft" })}
                >
                  Bỏ duyệt
                </Button>
              </div>
            ) : (
              <Button
                variant="primary"
                data-testid="approve-look-btn"
                className="text-xs py-1 px-3"
                onClick={() => {
                  if (lookLockText !== (c.look_lock ?? "")) {
                    update.mutate({ look_lock: lookLockText, look_status: "approved" });
                  } else {
                    update.mutate({ look_status: "approved" });
                  }
                }}
              >
                <Check className="w-3.5 h-3.5" /> Duyệt ngoại hình
              </Button>
            )}
          </div>
        </div>

        <textarea
          data-testid="look-lock-input"
          className="w-full bg-background border border-border rounded p-2 text-sm text-gray-200 resize-y min-h-[4rem]"
          placeholder="Ví dụ: young man, long black hair tied high, sharp red eyes, slim but athletic"
          value={lookLockText}
          onChange={(e) => setLookLockText(e.target.value)}
          onBlur={() => {
            if (lookLockText !== (c.look_lock ?? "")) {
              update.mutate({ look_lock: lookLockText });
            }
          }}
        />
      </div>

      {/* Row 3: Reference frames selection */}
      <div className="rounded-lg border border-border/80 bg-background/40 p-3 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-gray-200">
            Khung tham chiếu: {refIds.length} đã chọn (khuyên dùng 2–4 khung rõ mặt)
          </span>
          <span className="text-gray-400">Click khung để chọn / bỏ</span>
        </div>

        {suggestions.isLoading && <div className="text-xs text-gray-500">Đang tìm gợi ý khung...</div>}
        {suggestions.data && suggestions.data.length === 0 && (
          <div className="text-xs text-gray-500 italic">
            Chưa có gợi ý khung từ AI (chạy phân tích kịch bản để tự động tìm khung có nhân vật này).
          </div>
        )}

        {suggestions.data && suggestions.data.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {suggestions.data.map((f) => {
              const selected = refIds.includes(f.id);
              return (
                <button
                  key={f.id}
                  type="button"
                  data-testid="ref-frame-thumb"
                  onClick={() => toggleRefFrame(f.id)}
                  className={`relative rounded-md overflow-hidden border-2 transition-all ${
                    selected
                      ? "border-primary ring-2 ring-primary/40 scale-105"
                      : "border-border hover:border-gray-400 opacity-70 hover:opacity-100"
                  }`}
                  title={`Khung #${f.idx} (${f.frame_type || "scene"})`}
                >
                  <img src={f.image_url} alt={`Khung #${f.idx}`} className="w-20 h-20 object-cover" />
                  <span className="absolute bottom-0 right-0 bg-black/70 text-[10px] text-white px-1">
                    #{f.idx}
                  </span>
                  {selected && (
                    <span className="absolute top-0 right-0 bg-primary text-white p-0.5 rounded-bl">
                      <Check className="w-3 h-3" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Row 4: Outfits & Character Sheets */}
      <div className="space-y-3 pt-2 border-t border-border/60">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-200">Danh sách trang phục</span>
        </div>

        {/* Add outfit form */}
        <form
          className="flex flex-wrap gap-2 items-center bg-background/50 p-2.5 rounded-lg border border-border"
          onSubmit={(e) => {
            e.preventDefault();
            if (newOutfitName.trim()) {
              createOutfit.mutate({
                name_vi: newOutfitName.trim(),
                outfit_lock: newOutfitLock.trim(),
                short_id: newOutfitShortId.trim(),
                is_default: outfits.length === 0,
              });
              setNewOutfitName("");
              setNewOutfitLock("");
              setNewOutfitShortId("");
            }
          }}
        >
          <input
            className={`${input} w-44`}
            placeholder="Tên trang phục (vd: Áo đen)"
            value={newOutfitName}
            onChange={(e) => setNewOutfitName(e.target.value)}
          />
          <input
            className={`${input} flex-1 min-w-[12rem]`}
            placeholder="Khóa trang phục (outfit_lock: black robe with gold trim)"
            value={newOutfitLock}
            onChange={(e) => setNewOutfitLock(e.target.value)}
          />
          <input
            className={`${input} w-40`}
            placeholder="Tên ngắn (3-6 từ)"
            value={newOutfitShortId}
            onChange={(e) => setNewOutfitShortId(e.target.value)}
          />
          <Button variant="primary" type="submit" disabled={!newOutfitName.trim() || createOutfit.isPending}>
            <Plus className="w-3.5 h-3.5" /> Thêm trang phục
          </Button>
        </form>

        {/* Outfits list */}
        <div className="space-y-3">
          {outfits.map((o) => (
            <div key={o.id} className="rounded-lg border border-border/70 bg-background/30 p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <InlineText
                    value={o.name_vi}
                    className="w-40 font-medium"
                    onSave={(v) => v.trim() && updateOutfit.mutate({ oid: o.id, patch: { name_vi: v } })}
                  />
                  <span className="font-mono text-xs text-gray-500 w-24 truncate">{o.key}</span>
                  {o.is_default ? (
                    <span className="inline-flex items-center gap-1 text-amber-300 text-xs font-semibold px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800">
                      <Star className="w-3 h-3 fill-amber-300" /> Mặc định
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => updateOutfit.mutate({ oid: o.id, patch: { is_default: true } })}
                      className="text-xs text-gray-400 hover:text-gray-200 underline"
                    >
                      Đặt làm mặc định
                    </button>
                  )}
                  <InlineText
                    value={o.short_id ?? ""}
                    className="w-36"
                    placeholder="short_id (3-6 từ)…"
                    onSave={(v) => updateOutfit.mutate({ oid: o.id, patch: { short_id: v } })}
                  />
                </div>

                <Button
                  variant="danger"
                  title="Xóa trang phục"
                  disabled={o.is_default && outfits.filter((x) => x.is_default).length <= 1}
                  onClick={() =>
                    window.confirm(`Xóa trang phục "${o.name_vi}"?`) && delOutfit.mutate(o.id)
                  }
                >
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>

              <div>
                <InlineText
                  value={o.outfit_lock ?? ""}
                  className="w-full text-xs"
                  placeholder="Mô tả trang phục (outfit_lock: black robe, gold belt, sword on back…)"
                  onSave={(v) => updateOutfit.mutate({ oid: o.id, patch: { outfit_lock: v } })}
                />
              </div>

              {/* Sheet block for this outfit */}
              <SheetBlock
                target="outfits"
                id={o.id}
                sheetStatus={o.sheet_status}
                sheetUrl={o.sheet_url}
                refFrameCount={refIds.length}
                onRefresh={onUpdated}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Locations tab
// ---------------------------------------------------------------------------------------
function LocationsTab({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const key = ["locations", pid];
  const q = useQuery({ queryKey: key, queryFn: () => dialogueApi.locations(pid) });
  const chaptersQ = useQuery({ queryKey: ["chapters", pid], queryFn: () => studio.listChapters(pid) });

  const done = () => {
    qc.invalidateQueries({ queryKey: key });
    qc.invalidateQueries({ queryKey: ["bible", pid] });
  };

  const [form, setForm] = useState({ name_vi: "", aliases: "", location_lock: "" });
  const create = useMutation({
    mutationFn: () =>
      dialogueApi.createLocation(pid, {
        name_vi: form.name_vi.trim(),
        aliases: splitList(form.aliases),
        location_lock: form.location_lock.trim(),
        ref_frame_ids: [],
      }),
    onSuccess: () => {
      setForm({ name_vi: "", aliases: "", location_lock: "" });
      done();
    },
  });

  const locs = q.data ?? [];
  const latestChapterId = chaptersQ.data && chaptersQ.data.length > 0 ? chaptersQ.data[0].id : null;
  const framesQ = useQuery({
    queryKey: ["frames", latestChapterId],
    queryFn: () => (latestChapterId ? studio.getFrames(latestChapterId) : null),
    enabled: !!latestChapterId,
  });

  const allFrames: FrameItem[] = framesQ.data?.frames ?? [];

  return (
    <div className="space-y-4">
      <ErrorBox error={q.error || create.error} />

      <form
        className="flex flex-wrap gap-2 items-center rounded-xl border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (form.name_vi.trim()) create.mutate();
        }}
      >
        <input
          className={`${input} w-52`}
          placeholder="Tên bối cảnh (vd: Dược Viên)"
          value={form.name_vi}
          onChange={(e) => setForm({ ...form, name_vi: e.target.value })}
        />
        <input
          className={`${input} w-44`}
          placeholder="Tên khác (cách nhau dấu phẩy)"
          value={form.aliases}
          onChange={(e) => setForm({ ...form, aliases: e.target.value })}
        />
        <input
          className={`${input} flex-1 min-w-[14rem]`}
          placeholder="Khóa bối cảnh (location_lock: ancient temple, mist, night)"
          value={form.location_lock}
          onChange={(e) => setForm({ ...form, location_lock: e.target.value })}
        />
        <Button variant="primary" type="submit" disabled={!form.name_vi.trim() || create.isPending}>
          <Plus className="w-4 h-4" /> Thêm bối cảnh
        </Button>
      </form>

      {locs.length === 0 && (
        <div className="p-8 text-center text-sm text-gray-400 bg-surface rounded-xl border border-border">
          Chưa có bối cảnh nào. Thêm bối cảnh để tạo gói Sheet và đồng bộ không gian.
        </div>
      )}

      <div className="space-y-4">
        {locs.map((loc) => (
          <LocationCard
            key={loc.id}
            loc={loc}
            availableFrames={allFrames}
            onUpdated={done}
          />
        ))}
      </div>
    </div>
  );
}

function LocationCard({
  loc,
  availableFrames,
  onUpdated,
}: {
  loc: LocationItem;
  availableFrames: FrameItem[];
  onUpdated: () => void;
}) {
  const update = useMutation({
    mutationFn: (patch: Partial<LocationItem>) => dialogueApi.updateLocation(loc.id, patch),
    onSuccess: onUpdated,
  });
  const del = useMutation({
    mutationFn: () => dialogueApi.deleteLocation(loc.id),
    onSuccess: onUpdated,
  });

  const refIds = loc.ref_frame_ids ?? [];
  const toggleRefFrame = (fid: string) => {
    const next = refIds.includes(fid) ? refIds.filter((id) => id !== fid) : [...refIds, fid];
    update.mutate({ ref_frame_ids: next });
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-4 space-y-3">
      <ErrorBox error={update.error || del.error} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <InlineText
            value={loc.name_vi}
            className="w-48 font-semibold text-base"
            onSave={(v) => v.trim() && update.mutate({ name_vi: v })}
          />
          <span className="font-mono text-xs text-gray-500 w-28 truncate">{loc.key}</span>
          <InlineText
            value={(loc.aliases ?? []).join(", ")}
            className="w-48 text-xs"
            placeholder="tên gọi khác…"
            onSave={(v) => update.mutate({ aliases: splitList(v) })}
          />
        </div>
        <Button
          variant="danger"
          title="Xóa bối cảnh"
          onClick={() => window.confirm(`Xóa bối cảnh "${loc.name_vi}"?`) && del.mutate()}
        >
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-gray-300">
          Khóa bối cảnh (location_lock — EN: kiến trúc, ánh sáng, thời điểm):
        </label>
        <textarea
          className="w-full bg-background border border-border rounded p-2 text-sm text-gray-200 resize-y min-h-[3.5rem]"
          placeholder="Ví dụ: grand ancient Daoist temple hall, high carved pillars, mystical mist, night lighting"
          value={loc.location_lock ?? ""}
          onChange={(e) => update.mutate({ location_lock: e.target.value })}
        />
      </div>

      {/* Reference frames for location */}
      {availableFrames.length > 0 && (
        <div className="rounded-lg border border-border/80 bg-background/40 p-2.5 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-gray-200">
              Khung tham chiếu: {refIds.length} đã chọn
            </span>
            <span className="text-gray-400">Click khung để chọn / bỏ</span>
          </div>
          <div className="flex flex-wrap gap-2 pt-1 max-h-36 overflow-y-auto">
            {availableFrames.map((f) => {
              const selected = refIds.includes(f.id);
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => toggleRefFrame(f.id)}
                  className={`relative rounded-md overflow-hidden border-2 transition-all ${
                    selected
                      ? "border-primary ring-2 ring-primary/40 scale-105"
                      : "border-border hover:border-gray-400 opacity-70 hover:opacity-100"
                  }`}
                  title={`Khung #${f.idx}`}
                >
                  <img src={f.url} alt={`Khung #${f.idx}`} className="w-16 h-16 object-cover" />
                  <span className="absolute bottom-0 right-0 bg-black/70 text-[9px] text-white px-1">
                    #{f.idx}
                  </span>
                  {selected && (
                    <span className="absolute top-0 right-0 bg-primary text-white p-0.5 rounded-bl">
                      <Check className="w-2.5 h-2.5" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Location Sheet */}
      <SheetBlock
        target="locations"
        id={loc.id}
        sheetStatus={loc.sheet_status}
        sheetUrl={loc.sheet_url}
        refFrameCount={refIds.length}
        onRefresh={onUpdated}
      />
    </div>
  );
}

function GenderAge({
  gender,
  age,
  onChange,
}: {
  gender: Gender;
  age: AgeGroup;
  onChange: (p: { gender?: Gender; age_group?: AgeGroup }) => void;
}) {
  return (
    <>
      <select className={input} value={gender} onChange={(e) => onChange({ gender: e.target.value as Gender })}>
        {Object.entries(GENDER_LABEL).map(([v, l]) => (
          <option key={v} value={v}>
            {v === "unknown" ? "Giới tính ?" : l}
          </option>
        ))}
      </select>
      <select className={input} value={age} onChange={(e) => onChange({ age_group: e.target.value as AgeGroup })}>
        {Object.entries(AGE_LABEL).map(([v, l]) => (
          <option key={v} value={v}>
            {v === "unknown" ? "Tuổi ?" : l}
          </option>
        ))}
      </select>
    </>
  );
}
