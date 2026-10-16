import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, FolderKanban, MessageSquareText, Pencil, Plus, Scissors, Trash2, Upload } from "lucide-react";
import { formatBytes, rememberChapter, studio } from "../api/studio";
import { Button, Empty, ErrorBox, PageHeader, StatusBadge } from "../components/common";

function CreateInline({
  placeholder,
  cta,
  onCreate,
  pending,
}: {
  placeholder: string;
  cta: string;
  onCreate: (v: string) => void;
  pending: boolean;
}) {
  const [value, setValue] = useState("");
  const [hint, setHint] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <form
      className="flex flex-wrap items-start gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!value.trim()) {
          // Button stays clickable: an always-disabled button looked broken. Explain instead.
          setHint(true);
          input.current?.focus();
          return;
        }
        onCreate(value.trim());
        setValue("");
        setHint(false);
      }}
    >
      <div className="flex flex-col">
        <input
          ref={input}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (e.target.value.trim()) setHint(false);
          }}
          placeholder={placeholder}
          maxLength={200}
          className={`w-64 rounded-lg bg-surface border px-3 py-1.5 text-sm text-gray-100 placeholder:text-gray-500 focus:outline-none focus:border-primary ${
            hint ? "border-amber-400" : "border-border"
          }`}
        />
        {hint && <span className="text-xs text-amber-300 mt-1">Nhập tên trước rồi bấm {cta.toLowerCase()}</span>}
      </div>
      <Button variant="primary" type="submit" disabled={pending}>
        <Plus className="w-4 h-4" /> {pending ? "Đang tạo…" : cta}
      </Button>
    </form>
  );
}

export function ProjectsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: studio.listProjects,
  });
  const create = useMutation({
    mutationFn: studio.createProject,
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${p.id}`);
    },
  });

  return (
    <div className="p-8 max-w-6xl">
      <PageHeader
        title="Dự án"
        subtitle="Mỗi dự án là một bộ truyện; nhân vật và chiêu thức dùng chung cho mọi chapter."
        actions={
          <CreateInline
            placeholder="Tên bộ truyện…"
            cta="Tạo dự án"
            onCreate={(v) => create.mutate(v)}
            pending={create.isPending}
          />
        }
      />
      <div className="space-y-3">
        <ErrorBox error={error || create.error} />
        {isLoading ? (
          <div className="text-gray-400 text-sm">Đang tải…</div>
        ) : projects.length === 0 ? (
          <Empty icon={<FolderKanban className="w-6 h-6" />} title="Chưa có dự án nào">
            Nhập tên bộ truyện ở góc trên để bắt đầu.
          </Empty>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
            {projects.map((p) => (
              <Link
                key={p.id}
                to={`/projects/${p.id}`}
                className="block rounded-xl border border-border bg-surface p-5 hover:border-primary/60 transition"
              >
                <div className="flex items-center gap-2 text-gray-100 font-semibold">
                  <BookOpen className="w-4 h-4 text-primary" /> {p.name}
                </div>
                <div className="mt-3 text-xs text-gray-400 flex gap-4">
                  <span>{p.chapter_count ?? 0} chapter</span>
                  <span>{formatBytes(p.storage_bytes)}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ProjectDetailPage() {
  const { pid = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const project = useQuery({ queryKey: ["project", pid], queryFn: () => studio.getProject(pid) });
  const chapters = useQuery({ queryKey: ["chapters", pid], queryFn: () => studio.listChapters(pid) });

  const createCh = useMutation({
    mutationFn: (title: string) => studio.createChapter(pid, title),
    onSuccess: (ch) => {
      qc.invalidateQueries({ queryKey: ["chapters", pid] });
      rememberChapter(ch.id);
      navigate(`/chapters/${ch.id}/import`);
    },
  });
  const renameProject = useMutation({
    mutationFn: (name: string) => studio.renameProject(pid, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", pid] }),
  });
  const deleteProject = useMutation({
    mutationFn: () => studio.deleteProject(pid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects");
    },
  });
  const deleteChapter = useMutation({
    mutationFn: studio.deleteChapter,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chapters", pid] }),
  });
  const renameChapter = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => studio.renameChapter(id, title),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chapters", pid] }),
  });

  return (
    <div className="p-8 max-w-6xl">
      <PageHeader
        title={project.data?.name ?? "…"}
        subtitle={
          <Link to="/projects" className="hover:text-gray-200">
            ← Tất cả dự án
          </Link>
        }
        actions={
          <>
            <Link to={`/projects/${pid}/glossary`}>
              <Button>
                <BookOpen className="w-4 h-4" /> Thuật ngữ & nhân vật
              </Button>
            </Link>
            <Button
              onClick={() => {
                const v = window.prompt("Tên dự án mới", project.data?.name);
                if (v && v.trim()) renameProject.mutate(v.trim());
              }}
            >
              <Pencil className="w-4 h-4" /> Đổi tên
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                if (
                  window.confirm(
                    `Xóa dự án "${project.data?.name}"? File sẽ được chuyển vào thư mục trash (khôi phục tay được).`
                  )
                )
                  deleteProject.mutate();
              }}
            >
              <Trash2 className="w-4 h-4" /> Xóa dự án
            </Button>
          </>
        }
      />
      <div className="space-y-4">
        <ErrorBox
          error={project.error || chapters.error || createCh.error || deleteChapter.error || deleteProject.error}
        />
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Chapter</h2>
          <CreateInline
            placeholder="Tên chapter (vd: Chương 1)…"
            cta="Thêm chapter"
            onCreate={(v) => createCh.mutate(v)}
            pending={createCh.isPending}
          />
        </div>
        {chapters.data && chapters.data.length === 0 && (
          <Empty icon={<Upload className="w-6 h-6" />} title="Chưa có chapter">
            Thêm chapter rồi nhập ảnh từ URL hoặc thư mục.
          </Empty>
        )}
        <div className="divide-y divide-border rounded-xl border border-border bg-surface">
          {chapters.data?.map((ch) => (
            <div key={ch.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="min-w-0">
                <div className="font-medium text-gray-100">{ch.title}</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {ch.page_count} trang
                  {ch.excluded_page_count > 0 && ` (+${ch.excluded_page_count} bỏ)`} · {ch.frame_count} khung
                  {ch.busy_job_id && <span className="text-primary"> · đang xử lý…</span>}
                </div>
              </div>
              <StatusBadge status={ch.status} />
              <div className="ml-auto flex gap-2">
                <Link to={`/chapters/${ch.id}/import`} onClick={() => rememberChapter(ch.id)}>
                  <Button>
                    <Upload className="w-4 h-4" /> Nhập
                  </Button>
                </Link>
                <Link to={`/chapters/${ch.id}/frames`} onClick={() => rememberChapter(ch.id)}>
                  <Button disabled={ch.page_count === 0}>
                    <Scissors className="w-4 h-4" /> Khung
                  </Button>
                </Link>
                <Link to={`/chapters/${ch.id}/dialogue`} onClick={() => rememberChapter(ch.id)}>
                  <Button
                    disabled={!["frames_approved", "analyzing", "dialogue_draft", "dialogue_approved"].includes(ch.status)}
                    title="Kịch bản thoại (cần duyệt khung trước)"
                  >
                    <MessageSquareText className="w-4 h-4" /> Thoại
                  </Button>
                </Link>
                <Button
                  title="Đổi tên"
                  onClick={() => {
                    const v = window.prompt("Tên chapter mới", ch.title);
                    if (v && v.trim()) renameChapter.mutate({ id: ch.id, title: v.trim() });
                  }}
                >
                  <Pencil className="w-4 h-4" />
                </Button>
                <Button
                  variant="danger"
                  title="Xóa chapter"
                  onClick={() => {
                    if (window.confirm(`Xóa "${ch.title}"? File được chuyển vào thư mục trash.`))
                      deleteChapter.mutate(ch.id);
                  }}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
