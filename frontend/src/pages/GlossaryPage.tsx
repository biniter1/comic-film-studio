import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, GitMerge, Plus, Trash2, X } from "lucide-react";
import {
  AGE_LABEL,
  AddressRule,
  AgeGroup,
  Character,
  GENDER_LABEL,
  Gender,
  GlossaryTerm,
  ReviewStatus,
  TERM_KIND_LABEL,
  dialogueApi,
} from "../api/dialogue";
import { studio } from "../api/studio";
import { Button, ErrorBox, PageHeader } from "../components/common";

type Tab = "terms" | "address" | "characters";
const TABS: { id: Tab; label: string }[] = [
  { id: "terms", label: "Thuật ngữ" },
  { id: "address", label: "Xưng hô" },
  { id: "characters", label: "Nhân vật" },
];

const input = "bg-background border border-border rounded px-2 py-1 text-sm";

export function GlossaryPage() {
  const { pid = "" } = useParams();
  const [tab, setTab] = useState<Tab>("terms");
  const project = useQuery({ queryKey: ["project", pid], queryFn: () => studio.getProject(pid) });
  return (
    <div className="p-8 max-w-6xl">
      <PageHeader
        title={`Thuật ngữ · ${project.data?.name ?? "…"}`}
        subtitle={
          <span>
            <Link to={`/projects/${pid}`} className="hover:text-gray-200">
              ← Dự án
            </Link>{" "}
            · Dùng chung cho mọi chapter của dự án. AI đề xuất, bạn duyệt; chỉ mục đã duyệt mới được áp vào thoại.
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
  const empty = { speaker_key: "", listener_key: "", self_term: "", address_term: "" };
  const [form, setForm] = useState(empty);
  const create = useMutation({
    mutationFn: () => dialogueApi.createRule(pid, form),
    onSuccess: () => {
      setForm(empty);
      done();
    },
  });
  const name = (k: string) => chars.data?.find((c) => c.key === k)?.name ?? k;
  const charOptions = (chars.data ?? []).filter((c) => c.status !== "rejected");
  const valid = form.speaker_key && form.listener_key && form.self_term.trim() && form.address_term.trim();
  return (
    <div className="space-y-3">
      <ErrorBox error={q.error || update.error || del.error || create.error} />
      <div className="text-xs text-gray-400">
        Mỗi dòng: khi <b>A</b> nói với <b>B</b> thì A tự xưng là gì và gọi B là gì. AI biên tập thoại sẽ theo bảng này.
      </div>
      <form
        className="flex flex-wrap gap-2 items-center rounded-xl border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) create.mutate();
        }}
      >
        {(["speaker_key", "listener_key"] as const).map((k) => (
          <select key={k} className={input} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })}>
            <option value="">{k === "speaker_key" ? "Người nói…" : "Nói với…"}</option>
            {charOptions.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </select>
        ))}
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
function CharactersTab({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const key = ["characters", pid];
  const q = useQuery({ queryKey: key, queryFn: () => dialogueApi.characters(pid) });
  const done = () => qc.invalidateQueries({ queryKey: key });
  const update = useMutation({
    mutationFn: ({ id, p }: { id: string; p: Partial<Character> }) => dialogueApi.updateCharacter(id, p),
    onSuccess: done,
  });
  const del = useMutation({ mutationFn: (id: string) => dialogueApi.deleteCharacter(id), onSuccess: done });
  const merge = useMutation({
    mutationFn: ({ id, into }: { id: string; into: string }) => dialogueApi.mergeCharacter(id, into),
    onSuccess: done,
  });
  const empty = { name: "", gender: "unknown" as Gender, age_group: "unknown" as AgeGroup };
  const [form, setForm] = useState(empty);
  const create = useMutation({
    mutationFn: () => dialogueApi.createCharacter(pid, { ...form, name: form.name.trim() }),
    onSuccess: () => {
      setForm(empty);
      done();
    },
  });
  const chars = q.data ?? [];
  return (
    <div className="space-y-3">
      <ErrorBox error={q.error || update.error || del.error || merge.error || create.error} />
      <form
        className="flex flex-wrap gap-2 items-center rounded-xl border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (form.name.trim()) create.mutate();
        }}
      >
        <input
          className={`${input} w-56`}
          placeholder="Tên nhân vật"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <GenderAge
          gender={form.gender}
          age={form.age_group}
          onChange={(p) => setForm({ ...form, ...p })}
        />
        <Button variant="primary" type="submit" disabled={!form.name.trim() || create.isPending}>
          <Plus className="w-4 h-4" /> Thêm
        </Button>
      </form>
      <div className="rounded-xl border border-border bg-surface divide-y divide-border">
        {chars.length === 0 && <div className="p-4 text-sm text-gray-400">Chưa có nhân vật nào.</div>}
        {chars.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center gap-2 px-3 py-2" data-testid="character-row">
            <InlineText value={c.name} className="w-40 font-medium" onSave={(v) => v.trim() && update.mutate({ id: c.id, p: { name: v } })} />
            <span className="font-mono text-[11px] text-gray-500 w-28 truncate" title="key">
              {c.key}
            </span>
            <GenderAge
              gender={c.gender}
              age={c.age_group}
              onChange={(p) => update.mutate({ id: c.id, p })}
            />
            <InlineText
              value={c.aliases.join(", ")}
              className="w-44"
              placeholder="bí danh / cách gọi khác"
              onSave={(v) => update.mutate({ id: c.id, p: { aliases: splitList(v) } })}
            />
            <InlineText
              value={c.voice_style ?? ""}
              className="w-40"
              placeholder="kiểu giọng"
              onSave={(v) => update.mutate({ id: c.id, p: { voice_style: v } })}
            />
            <span className="text-xs text-gray-500">{c.line_count ?? 0} câu</span>
            <StatusPill status={c.status} />
            <ReviewButtons status={c.status} onSet={(s) => update.mutate({ id: c.id, p: { status: s } })} />
            <select
              className={`${input} w-28`}
              value=""
              title="Gộp: hai nhân vật thực ra là một người"
              onChange={(e) =>
                e.target.value &&
                window.confirm(`Gộp "${c.name}" vào nhân vật đã chọn? Câu thoại sẽ chuyển sang.`) &&
                merge.mutate({ id: c.id, into: e.target.value })
              }
            >
              <option value="">⇢ Gộp vào…</option>
              {chars
                .filter((o) => o.id !== c.id)
                .map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
            </select>
            <Button
              variant="danger"
              title="Xóa"
              onClick={() => window.confirm(`Xóa "${c.name}"? Câu thoại giữ tên này dạng nhân vật phụ.`) && del.mutate(c.id)}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        ))}
      </div>
      <div className="text-xs text-gray-500 flex items-center gap-1">
        <GitMerge className="w-3.5 h-3.5" /> AI có thể nhận một người thành hai (tên khác nhau) — dùng “Gộp vào…” để hợp lại.
      </div>
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
