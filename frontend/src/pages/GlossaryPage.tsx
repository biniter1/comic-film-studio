import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Crop,
  Download,
  Plus,
  Sparkles,
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
  CharacterRef,
  CharacterRole,
  FrameSuggestion,
  GENDER_LABEL,
  Gender,
  GlossaryTerm,
  HEIGHT_CLASS_LABEL,
  HeightClass,
  LocationItem,
  ROLE_LABEL,
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
// ---------------------------------------------------------------------------------------
// Crop Reference Modal
// ---------------------------------------------------------------------------------------
function CropRefModal({
  chid,
  suggestions,
  initialFrameId,
  outfits,
  onClose,
  onSuccess,
}: {
  chid: string;
  suggestions: FrameSuggestion[];
  initialFrameId?: string;
  outfits: CharacterOutfit[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [selectedFrameId, setSelectedFrameId] = useState<string>(
    initialFrameId || suggestions[0]?.id || ""
  );
  const [outfitId, setOutfitId] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const [x0, setX0] = useState<number>(0);
  const [y0, setY0] = useState<number>(0);
  const [x1, setX1] = useState<number>(200);
  const [y1, setY1] = useState<number>(200);
  const [imgNaturalSize, setImgNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const imgRef = useRef<HTMLImageElement>(null);
  const selectedFrame = suggestions.find((s) => s.id === selectedFrameId) ?? suggestions[0];

  const cropMut = useMutation({
    mutationFn: () =>
      dialogueApi.cropRef(chid, {
        frame_id: selectedFrameId,
        x0,
        y0,
        x1,
        y1,
        outfit_id: outfitId || undefined,
        note: note.trim() || undefined,
      }),
    onSuccess: () => {
      onSuccess();
      onClose();
    },
    onError: (err: unknown) => {
      const e = err as { message_vi?: string; message?: string };
      setError(e.message_vi || e.message || "Lỗi cắt ảnh");
    },
  });

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const im = e.currentTarget;
    setImgNaturalSize({ w: im.naturalWidth, h: im.naturalHeight });
    const w = im.naturalWidth;
    const h = im.naturalHeight;
    const boxW = Math.min(250, Math.max(64, Math.floor(w * 0.5)));
    const boxH = Math.min(250, Math.max(64, Math.floor(h * 0.5)));
    const startX = Math.max(0, Math.floor((w - boxW) / 2));
    const startY = Math.max(0, Math.floor((h - boxH) / 2));
    setX0(startX);
    setY0(startY);
    setX1(startX + boxW);
    setY1(startY + boxH);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!imgRef.current || !imgNaturalSize) return;
    const rect = imgRef.current.getBoundingClientRect();
    const scaleX = imgNaturalSize.w / rect.width;
    const scaleY = imgNaturalSize.h / rect.height;
    const clickX = Math.max(0, Math.min(imgNaturalSize.w, Math.round((e.clientX - rect.left) * scaleX)));
    const clickY = Math.max(0, Math.min(imgNaturalSize.h, Math.round((e.clientY - rect.top) * scaleY)));
    setIsDragging(true);
    setDragStart({ x: clickX, y: clickY });
    setX0(clickX);
    setY0(clickY);
    setX1(clickX);
    setY1(clickY);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging || !dragStart || !imgRef.current || !imgNaturalSize) return;
    const rect = imgRef.current.getBoundingClientRect();
    const scaleX = imgNaturalSize.w / rect.width;
    const scaleY = imgNaturalSize.h / rect.height;
    const currentX = Math.max(0, Math.min(imgNaturalSize.w, Math.round((e.clientX - rect.left) * scaleX)));
    const currentY = Math.max(0, Math.min(imgNaturalSize.h, Math.round((e.clientY - rect.top) * scaleY)));
    setX0(Math.min(dragStart.x, currentX));
    setY0(Math.min(dragStart.y, currentY));
    setX1(Math.max(dragStart.x, currentX));
    setY1(Math.max(dragStart.y, currentY));
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    setDragStart(null);
  };

  const width = x1 - x0;
  const height = y1 - y0;
  const isValid =
    selectedFrameId &&
    width >= 64 &&
    height >= 64 &&
    imgNaturalSize &&
    x0 >= 0 &&
    y0 >= 0 &&
    x1 <= imgNaturalSize.w &&
    y1 <= imgNaturalSize.h;

  const overlayLeft = imgNaturalSize ? `${(x0 / imgNaturalSize.w) * 100}%` : "0%";
  const overlayTop = imgNaturalSize ? `${(y0 / imgNaturalSize.h) * 100}%` : "0%";
  const overlayWidth = imgNaturalSize ? `${(width / imgNaturalSize.w) * 100}%` : "0%";
  const overlayHeight = imgNaturalSize ? `${(height / imgNaturalSize.h) * 100}%` : "0%";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
      <div className="bg-surface border border-border rounded-xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Crop className="w-5 h-5 text-primary" />
            <h3 className="font-semibold text-gray-100">Cắt ảnh tham chiếu từ khung truyện</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-gray-400 hover:text-white hover:bg-background"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto flex-1">
          {error && (
            <div className="p-2.5 rounded bg-red-950/80 border border-red-800 text-xs text-red-300">
              {error}
            </div>
          )}

          {/* Frame selection */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-gray-300">
              1. Chọn khung truyện chứa nhân vật:
            </label>
            {suggestions.length === 0 ? (
              <div className="text-xs text-amber-300 bg-amber-950/40 p-2.5 rounded border border-amber-900/60">
                Chưa có gợi ý khung từ AI cho nhân vật này. Chạy phân tích kịch bản để tự động tìm khung.
              </div>
            ) : (
              <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto p-1.5 bg-background/50 rounded border border-border">
                {suggestions.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    data-testid={`select-frame-${f.id}`}
                    onClick={() => {
                      setSelectedFrameId(f.id);
                      setImgNaturalSize(null);
                    }}
                    className={`relative rounded overflow-hidden border-2 transition-all ${
                      selectedFrameId === f.id
                        ? "border-primary ring-2 ring-primary/40 scale-105"
                        : "border-border opacity-70 hover:opacity-100"
                    }`}
                  >
                    <img src={f.image_url} alt={`Khung #${f.idx}`} className="w-16 h-16 object-cover" />
                    <span className="absolute bottom-0 right-0 bg-black/70 text-[9px] text-white px-1">
                      #{f.idx}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Frame image + crop area */}
          {selectedFrame && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>2. Kéo chọn vùng trên ảnh (tối thiểu 64×64 px):</span>
                {imgNaturalSize && (
                  <span>
                    Khung: {imgNaturalSize.w}×{imgNaturalSize.h} px | Vùng cắt: {width}×{height} px{" "}
                    {(width < 64 || height < 64) && (
                      <span className="text-amber-400 font-semibold">(Tối thiểu 64×64 px)</span>
                    )}
                  </span>
                )}
              </div>

              <div
                className="relative border border-border rounded overflow-hidden bg-black/50 select-none cursor-crosshair flex items-center justify-center max-h-[380px]"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
              >
                <img
                  ref={imgRef}
                  src={selectedFrame.image_url}
                  alt="Frame for crop"
                  onLoad={handleImageLoad}
                  className="max-h-[380px] max-w-full object-contain pointer-events-none"
                />
                {imgNaturalSize && width > 0 && height > 0 && (
                  <div
                    className="absolute border-2 border-primary bg-primary/20 pointer-events-none"
                    style={{
                      left: overlayLeft,
                      top: overlayTop,
                      width: overlayWidth,
                      height: overlayHeight,
                    }}
                  >
                    <span className="absolute top-0 left-0 bg-primary text-[10px] text-white px-1">
                      {width}×{height}
                    </span>
                  </div>
                )}
              </div>

              {/* Coordinate manual inputs */}
              <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                <span className="text-gray-400 font-medium">Tọa độ:</span>
                <label className="flex items-center gap-1">
                  x0:
                  <input
                    type="number"
                    data-testid="crop-x0"
                    className={`${input} w-16 py-0.5 text-xs`}
                    value={x0}
                    onChange={(e) => setX0(Number(e.target.value))}
                  />
                </label>
                <label className="flex items-center gap-1">
                  y0:
                  <input
                    type="number"
                    data-testid="crop-y0"
                    className={`${input} w-16 py-0.5 text-xs`}
                    value={y0}
                    onChange={(e) => setY0(Number(e.target.value))}
                  />
                </label>
                <label className="flex items-center gap-1">
                  x1:
                  <input
                    type="number"
                    data-testid="crop-x1"
                    className={`${input} w-16 py-0.5 text-xs`}
                    value={x1}
                    onChange={(e) => setX1(Number(e.target.value))}
                  />
                </label>
                <label className="flex items-center gap-1">
                  y1:
                  <input
                    type="number"
                    data-testid="crop-y1"
                    className={`${input} w-16 py-0.5 text-xs`}
                    value={y1}
                    onChange={(e) => setY1(Number(e.target.value))}
                  />
                </label>
                <select
                  className={`${input} text-xs py-0.5`}
                  value={outfitId}
                  onChange={(e) => setOutfitId(e.target.value)}
                >
                  <option value="">Gắn trang phục (tùy chọn)…</option>
                  {outfits.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name_vi}
                    </option>
                  ))}
                </select>
                <input
                  className={`${input} flex-1 min-w-[8rem] text-xs py-0.5`}
                  placeholder="Ghi chú (tùy chọn)…"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border bg-background/50 flex items-center justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button
            variant="primary"
            data-testid="save-crop-btn"
            disabled={!isValid || cropMut.isPending}
            onClick={() => cropMut.mutate()}
          >
            <Check className="w-4 h-4" /> Lưu ảnh tham chiếu
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Characters tab (Cards with Look Lock, Character Refs, AI Profile & Outfits)
// ---------------------------------------------------------------------------------------
function CharactersTab({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const key = ["bible", pid];
  const q = useQuery({ queryKey: key, queryFn: () => dialogueApi.bible(pid) });
  const done = () => {
    qc.invalidateQueries({ queryKey: key });
    qc.invalidateQueries({ queryKey: ["characters", pid] });
  };

  const [roleFilter, setRoleFilter] = useState<string>("all");

  const empty = {
    name: "",
    gender: "unknown" as Gender,
    age_group: "unknown" as AgeGroup,
    height_class: "average" as HeightClass,
    role: "supporting" as CharacterRole,
    is_group: false,
    group_size_hint: "",
  };
  const [form, setForm] = useState(empty);
  const create = useMutation({
    mutationFn: () =>
      dialogueApi.createCharacter(pid, {
        ...form,
        name: form.name.trim(),
        group_size_hint: form.is_group ? form.group_size_hint.trim() : undefined,
      }),
    onSuccess: () => {
      setForm(empty);
      done();
    },
  });

  const chars = q.data?.characters ?? [];
  const filteredChars = chars.filter((c) => roleFilter === "all" || c.role === roleFilter);

  return (
    <div className="space-y-4">
      <ErrorBox error={q.error || create.error} />

      {/* Role filter bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-gray-400 mr-1 font-medium">Lọc hạng:</span>
          {[
            { id: "all", label: "Tất cả" },
            { id: "main", label: "Chính" },
            { id: "supporting", label: "Phụ" },
            { id: "extra", label: "Quần chúng" },
          ].map((f) => (
            <button
              key={f.id}
              type="button"
              data-testid={`filter-role-${f.id}`}
              onClick={() => setRoleFilter(f.id)}
              className={`px-3 py-1 rounded text-xs transition-colors ${
                roleFilter === f.id
                  ? "bg-primary text-white font-semibold"
                  : "bg-surface hover:bg-surface/80 text-gray-300 border border-border"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-500">
          Hiển thị {filteredChars.length}/{chars.length} nhân vật
        </span>
      </div>

      {/* Add character form */}
      <form
        className="flex flex-wrap gap-2 items-center rounded-xl border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (form.name.trim()) create.mutate();
        }}
      >
        <input
          className={`${input} w-48`}
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
        <select
          className={input}
          value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value as CharacterRole })}
        >
          {Object.entries(ROLE_LABEL).map(([val, label]) => (
            <option key={val} value={val}>
              Hạng: {label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_group}
            onChange={(e) => setForm({ ...form, is_group: e.target.checked })}
          />
          Nhóm
        </label>
        {form.is_group && (
          <input
            className={`${input} w-32`}
            placeholder="Quy mô (2-3 người)"
            value={form.group_size_hint}
            onChange={(e) => setForm({ ...form, group_size_hint: e.target.value })}
          />
        )}
        <Button variant="primary" type="submit" disabled={!form.name.trim() || create.isPending}>
          <Plus className="w-4 h-4" /> Thêm nhân vật
        </Button>
      </form>

      {chars.length === 0 && (
        <div className="p-8 text-center text-sm text-gray-400 bg-surface rounded-xl border border-border">
          Chưa có nhân vật nào. Hãy thêm nhân vật hoặc chạy phân tích chapter.
        </div>
      )}

      {chars.length > 0 && filteredChars.length === 0 && (
        <div className="p-6 text-center text-sm text-gray-400 bg-surface rounded-xl border border-border">
          Không có nhân vật nào thuộc hạng này.
        </div>
      )}

      <div className="space-y-4">
        {filteredChars.map((c) => (
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

  // Refs mutations
  const uploadRefMut = useMutation({
    mutationFn: (file: File) => dialogueApi.uploadRef(c.id, file),
    onSuccess: onUpdated,
  });
  const delRefMut = useMutation({
    mutationFn: (rid: string) => dialogueApi.deleteRef(rid),
    onSuccess: onUpdated,
  });
  const updateRefMut = useMutation({
    mutationFn: ({ rid, patch }: { rid: string; patch: Partial<CharacterRef> }) =>
      dialogueApi.updateRef(rid, patch),
    onSuccess: onUpdated,
  });

  // AI Look Profile Mutation
  const profileMut = useMutation({
    mutationFn: () => dialogueApi.requestLookProfile(c.id),
    onSuccess: async (data) => {
      if (data?.job_id) {
        let attempts = 0;
        const interval = setInterval(async () => {
          attempts++;
          try {
            const res = await fetch(`/api/jobs/${data.job_id}`);
            if (res.ok) {
              const j = await res.json();
              if (["succeeded", "failed", "cancelled"].includes(j.status)) {
                clearInterval(interval);
                onUpdated();
              }
            }
          } catch {
            // ignore
          }
          if (attempts > 60) clearInterval(interval);
        }, 500);
      }
      onUpdated();
    },
  });

  // Proposal mutations
  const applyProposalMut = useMutation({
    mutationFn: (fields?: string[]) => dialogueApi.applyProposal(c.id, fields),
    onSuccess: onUpdated,
  });
  const dismissProposalMut = useMutation({
    mutationFn: () => dialogueApi.updateCharacter(c.id, { profile_proposal: null }),
    onSuccess: onUpdated,
  });

  // Local state for look_lock
  const [lookLockText, setLookLockText] = useState(c.look_lock ?? "");
  const [newOutfitName, setNewOutfitName] = useState("");
  const [newOutfitLock, setNewOutfitLock] = useState("");
  const [newOutfitShortId, setNewOutfitShortId] = useState("");
  const [cropModalOpen, setCropModalOpen] = useState(false);
  const [selectedCropFrameId, setSelectedCropFrameId] = useState<string>("");

  useEffect(() => {
    setLookLockText(c.look_lock ?? "");
  }, [c.look_lock]);

  const words = countWords(lookLockText);
  const refs = c.refs ?? [];
  const outfits = c.outfits ?? [];
  const defaultOutfit = outfits.find((o) => o.is_default) ?? outfits[0];

  const swapOrder = (r1: CharacterRef, r2: CharacterRef) => {
    const o1 = r1.order;
    const o2 = r2.order;
    updateRefMut.mutate({ rid: r1.id, patch: { order: o2 } });
    updateRefMut.mutate({ rid: r2.id, patch: { order: o1 } });
  };

  return (
    <div
      className="rounded-xl border border-border bg-surface p-4 space-y-4"
      data-testid="character-row"
    >
      <ErrorBox
        error={
          update.error ||
          del.error ||
          merge.error ||
          createOutfit.error ||
          uploadRefMut.error ||
          delRefMut.error ||
          profileMut.error ||
          applyProposalMut.error
        }
      />

      {/* Row 1: Basic info */}
      <div className="flex flex-wrap items-center gap-2">
        <InlineText
          value={c.name}
          className="w-40 font-semibold text-base"
          onSave={(v) => v.trim() && update.mutate({ name: v })}
        />
        <span className="font-mono text-xs text-gray-500 w-24 truncate" title="key">
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

        {/* Character Role Select */}
        <select
          className={`${input} text-xs font-semibold`}
          data-testid="character-role-select"
          value={c.role || "supporting"}
          onChange={(e) =>
            update.mutate({ role: e.target.value as CharacterRole, role_source: "user" })
          }
        >
          {Object.entries(ROLE_LABEL).map(([val, label]) => (
            <option key={val} value={val}>
              {label}
            </option>
          ))}
        </select>

        {/* Group checkbox */}
        <label className="flex items-center gap-1 text-xs text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            data-testid="character-is-group"
            checked={c.is_group ?? false}
            onChange={(e) => update.mutate({ is_group: e.target.checked })}
          />
          Nhóm
        </label>
        {c.is_group && (
          <InlineText
            value={c.group_size_hint ?? ""}
            className="w-28 text-xs"
            placeholder="vd: 2–3 người"
            onSave={(v) => update.mutate({ group_size_hint: v })}
          />
        )}

        <InlineText
          value={(c.aliases ?? []).join(", ")}
          className="w-36"
          placeholder="bí danh…"
          onSave={(v) => update.mutate({ aliases: splitList(v) })}
        />
        <InlineText
          value={c.voice_style ?? ""}
          className="w-32"
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

      {/* Row 3: Khối Ảnh tham chiếu */}
      <div className="rounded-lg border border-border/80 bg-background/40 p-3 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-200">
              Ảnh tham chiếu: {refs.length} ảnh
            </span>
            <span className="text-xs text-gray-400">
              (dùng cho gói Sheet và AI tạo hồ sơ ngoại hình)
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              data-testid="crop-ref-btn"
              className="text-xs py-1 px-2.5"
              onClick={() => {
                setSelectedCropFrameId(suggestions.data?.[0]?.id || "");
                setCropModalOpen(true);
              }}
            >
              <Crop className="w-3.5 h-3.5" /> Cắt từ khung
            </Button>

            <label
              data-testid="upload-ref-btn"
              className="cursor-pointer inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded border border-border bg-surface hover:border-gray-400 text-gray-300 transition-colors"
            >
              <Upload className="w-3.5 h-3.5" /> Tải ảnh lên
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadRefMut.mutate(file);
                  e.target.value = "";
                }}
              />
            </label>

            <Button
              variant="primary"
              data-testid="ai-look-profile-btn"
              className="text-xs py-1 px-2.5"
              disabled={refs.length === 0 || profileMut.isPending}
              onClick={() => profileMut.mutate()}
              title={
                refs.length === 0
                  ? "Cần ít nhất 1 ảnh tham chiếu"
                  : "AI phân tích ảnh tham chiếu để tạo hồ sơ ngoại hình"
              }
            >
              <Sparkles className="w-3.5 h-3.5" /> AI tạo hồ sơ ngoại hình (~3 credit)
            </Button>
          </div>
        </div>

        {/* Suggested frames quick-access */}
        {suggestions.data && suggestions.data.length > 0 && (
          <div className="space-y-1">
            <span className="text-[11px] text-gray-400">
              Gợi ý khung chứa nhân vật (click để cắt ảnh tham chiếu):
            </span>
            <div className="flex flex-wrap gap-2 pt-0.5">
              {suggestions.data.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  data-testid="ref-frame-thumb"
                  onClick={() => {
                    setSelectedCropFrameId(f.id);
                    setCropModalOpen(true);
                  }}
                  className="relative rounded-md overflow-hidden border-2 border-border hover:border-primary opacity-80 hover:opacity-100 transition-all hover:scale-105"
                  title={`Khung #${f.idx} (${f.frame_type || "scene"}) - Bấm để cắt tham chiếu`}
                >
                  <img src={f.image_url} alt={`Khung #${f.idx}`} className="w-16 h-16 object-cover" />
                  <span className="absolute bottom-0 right-0 bg-black/70 text-[9px] text-white px-1">
                    #{f.idx}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* References grid */}
        {refs.length === 0 ? (
          <div className="text-xs text-gray-500 italic py-1">
            Chưa có ảnh tham chiếu. Bấm "Cắt từ khung" hoặc "Tải ảnh lên" để tạo ảnh tham chiếu cho nhân vật.
          </div>
        ) : (
          <div className="flex flex-wrap gap-2.5 pt-1">
            {refs.map((r, idx) => (
              <div
                key={r.id}
                data-testid="char-ref-item"
                className="group relative rounded-lg overflow-hidden border border-border bg-black/40 w-24 h-24 flex items-center justify-center shadow"
              >
                <img
                  src={r.image_url}
                  alt={`Ref #${r.order}`}
                  className="w-full h-full object-cover"
                />
                <span className="absolute top-1 left-1 bg-black/75 text-[10px] text-white px-1 rounded font-mono">
                  #{r.order}
                </span>
                {r.outfit_id && (
                  <span className="absolute bottom-1 left-1 bg-primary/80 text-[9px] text-white px-1 rounded truncate max-w-[80px]">
                    {outfits.find((o) => o.id === r.outfit_id)?.name_vi || "Outfit"}
                  </span>
                )}
                <div className="absolute inset-0 bg-black/65 opacity-0 group-hover:opacity-100 flex items-center justify-center gap-1 transition-opacity">
                  {idx > 0 && (
                    <button
                      type="button"
                      title="Chuyển sang trước"
                      onClick={() => swapOrder(r, refs[idx - 1])}
                      className="p-1 rounded bg-surface/80 hover:bg-surface text-gray-200"
                    >
                      <ArrowLeft className="w-3 h-3" />
                    </button>
                  )}
                  {idx < refs.length - 1 && (
                    <button
                      type="button"
                      title="Chuyển sang sau"
                      onClick={() => swapOrder(r, refs[idx + 1])}
                      className="p-1 rounded bg-surface/80 hover:bg-surface text-gray-200"
                    >
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                  <button
                    type="button"
                    data-testid="delete-ref-btn"
                    title="Xóa ảnh tham chiếu"
                    onClick={() => delRefMut.mutate(r.id)}
                    className="p-1 rounded bg-red-950/80 hover:bg-red-900 text-red-300"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* AI Proposal Comparison Table */}
        {c.profile_proposal && (
          <div className="mt-3 rounded-lg border border-primary/40 bg-primary/5 p-3 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-bold text-primary flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" /> Bản đề xuất hồ sơ ngoại hình từ AI
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="primary"
                  className="text-xs py-0.5 px-2.5"
                  data-testid="apply-all-proposal"
                  onClick={() => applyProposalMut.mutate(undefined)}
                >
                  <Check className="w-3 h-3" /> Áp dụng tất cả
                </Button>
                <Button
                  variant="secondary"
                  className="text-xs py-0.5 px-2 text-gray-400 hover:text-red-300"
                  data-testid="dismiss-proposal"
                  onClick={() => dismissProposalMut.mutate()}
                >
                  <X className="w-3 h-3" /> Bỏ qua đề xuất
                </Button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="border-b border-border/60 text-gray-400">
                    <th className="py-1 px-2 font-medium w-32">Trường</th>
                    <th className="py-1 px-2 font-medium">Hiện tại</th>
                    <th className="py-1 px-2 font-medium text-emerald-400">AI Đề xuất</th>
                    <th className="py-1 px-2 font-medium w-24 text-right">Hành động</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  <tr>
                    <td className="py-1.5 px-2 text-gray-300 font-medium">Khóa ngoại hình</td>
                    <td className="py-1.5 px-2 text-gray-400">{c.look_lock || "—"}</td>
                    <td className="py-1.5 px-2 text-emerald-300 font-mono text-[11px]">
                      {c.profile_proposal.look_lock}
                    </td>
                    <td className="py-1.5 px-2 text-right">
                      <Button
                        variant="secondary"
                        className="text-[11px] py-0.5 px-2"
                        data-testid="apply-look-lock"
                        onClick={() => applyProposalMut.mutate(["look_lock"])}
                      >
                        Áp dụng
                      </Button>
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1.5 px-2 text-gray-300 font-medium">Dáng người</td>
                    <td className="py-1.5 px-2 text-gray-400">
                      {HEIGHT_CLASS_LABEL[c.height_class || "average"]}
                    </td>
                    <td className="py-1.5 px-2 text-emerald-300">
                      {HEIGHT_CLASS_LABEL[c.profile_proposal.height_class as HeightClass] ||
                        c.profile_proposal.height_class}
                    </td>
                    <td className="py-1.5 px-2 text-right">
                      <Button
                        variant="secondary"
                        className="text-[11px] py-0.5 px-2"
                        data-testid="apply-height-class"
                        onClick={() => applyProposalMut.mutate(["height_class"])}
                      >
                        Áp dụng
                      </Button>
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1.5 px-2 text-gray-300 font-medium">Khóa trang phục</td>
                    <td className="py-1.5 px-2 text-gray-400">{defaultOutfit?.outfit_lock || "—"}</td>
                    <td className="py-1.5 px-2 text-emerald-300 font-mono text-[11px]">
                      {c.profile_proposal.outfit_lock}
                    </td>
                    <td className="py-1.5 px-2 text-right">
                      <Button
                        variant="secondary"
                        className="text-[11px] py-0.5 px-2"
                        data-testid="apply-outfit-lock"
                        onClick={() => applyProposalMut.mutate(["outfit_lock"])}
                      >
                        Áp dụng
                      </Button>
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1.5 px-2 text-gray-300 font-medium">Tên ngắn trang phục</td>
                    <td className="py-1.5 px-2 text-gray-400">{defaultOutfit?.short_id || "—"}</td>
                    <td className="py-1.5 px-2 text-emerald-300">
                      {c.profile_proposal.short_id}
                    </td>
                    <td className="py-1.5 px-2 text-right">
                      <Button
                        variant="secondary"
                        className="text-[11px] py-0.5 px-2"
                        data-testid="apply-short-id"
                        onClick={() => applyProposalMut.mutate(["short_id"])}
                      >
                        Áp dụng
                      </Button>
                    </td>
                  </tr>
                  {c.profile_proposal.palette && (
                    <tr>
                      <td className="py-1.5 px-2 text-gray-300 font-medium">Bảng màu</td>
                      <td className="py-1.5 px-2 text-gray-400">—</td>
                      <td className="py-1.5 px-2 text-emerald-300" colSpan={2}>
                        {c.profile_proposal.palette.join(", ")}
                      </td>
                    </tr>
                  )}
                  {c.profile_proposal.distinctive && (
                    <tr>
                      <td className="py-1.5 px-2 text-gray-300 font-medium">Đặc điểm nhận dạng</td>
                      <td className="py-1.5 px-2 text-gray-400">—</td>
                      <td className="py-1.5 px-2 text-emerald-300" colSpan={2}>
                        {c.profile_proposal.distinctive.join("; ")}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Row 4: Outfits & Character Sheets */}
      {c.is_group ? (
        <div className="p-3 text-xs text-gray-500 italic bg-background/20 rounded-lg border border-border/40">
          Nhân vật nhóm không dùng bảng mẫu (sheet).
        </div>
      ) : (
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
                  refFrameCount={refs.length}
                  onRefresh={onUpdated}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Crop Ref Modal */}
      {cropModalOpen && (
        <CropRefModal
          chid={c.id}
          suggestions={suggestions.data ?? []}
          initialFrameId={selectedCropFrameId}
          outfits={outfits}
          onClose={() => setCropModalOpen(false)}
          onSuccess={onUpdated}
        />
      )}
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
