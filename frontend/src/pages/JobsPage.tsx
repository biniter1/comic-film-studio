import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Job } from "../api/client";
import { Play, RotateCw, XCircle, FileText, CheckCircle2, Clock, AlertTriangle, X } from "lucide-react";

export function JobsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedLogJob, setSelectedLogJob] = useState<Job | null>(null);
  const [logContent, setLogContent] = useState<string>("");
  const [isLoadingLog, setIsLoadingLog] = useState<boolean>(false);

  // Fetch jobs
  const { data: jobs = [], isLoading, error } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.getJobs(),
    refetchInterval: 10000, // Background fallback polling
  });

  // Create demo job mutation
  const createDemoMutation = useMutation({
    mutationFn: () => api.createDemoJob({ duration_s: 5 }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  // Retry job mutation
  const retryMutation = useMutation({
    mutationFn: (id: string) => api.retryJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  // Cancel job mutation
  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.cancelJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const handleOpenLog = async (job: Job) => {
    setSelectedLogJob(job);
    setIsLoadingLog(true);
    try {
      const text = await api.getJobLog(job.id);
      setLogContent(text);
    } catch {
      setLogContent("Không thể tải file log.");
    } finally {
      setIsLoadingLog(false);
    }
  };

  const filteredJobs = jobs.filter((j) => {
    if (statusFilter === "all") return true;
    return j.status === statusFilter;
  });

  const getStatusBadge = (status: Job["status"]) => {
    switch (status) {
      case "running":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
            Đang chạy
          </span>
        );
      case "succeeded":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Thành công
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <AlertTriangle className="w-3.5 h-3.5" />
            Lỗi
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-500/10 text-gray-400 border border-gray-500/20">
            <XCircle className="w-3.5 h-3.5" />
            Đã hủy
          </span>
        );
      case "queued":
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Clock className="w-3.5 h-3.5" />
            Hàng chờ
          </span>
        );
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Tiến trình chạy nền (Jobs)</h1>
          <p className="text-sm text-gray-400 mt-1">
            Theo dõi, thử nghiệm và quản lý các tác vụ xử lý của Comic Film Studio
          </p>
        </div>

        <button
          onClick={() => createDemoMutation.mutate()}
          disabled={createDemoMutation.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50"
        >
          <Play className="w-4 h-4 fill-current" />
          {createDemoMutation.isPending ? "Đang tạo..." : "Tạo job thử"}
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
        {[
          { key: "all", label: "Tất cả" },
          { key: "running", label: "Đang chạy" },
          { key: "queued", label: "Hàng chờ" },
          { key: "succeeded", label: "Thành công" },
          { key: "failed", label: "Lỗi" },
          { key: "cancelled", label: "Đã hủy" },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setStatusFilter(tab.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
              statusFilter === tab.key
                ? "bg-surface-raised text-white border border-border"
                : "text-gray-400 hover:text-gray-200 hover:bg-surface/50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Jobs Table */}
      <div className="bg-surface border border-border rounded-xl overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-12 text-center text-gray-400">Đang tải danh sách jobs...</div>
        ) : error ? (
          <div className="p-12 text-center text-rose-400">Lỗi khi tải jobs: {String(error)}</div>
        ) : filteredJobs.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            Không có job nào phù hợp bộ lọc. Hãy bấm <strong>"Tạo job thử"</strong> để bắt đầu.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-raised/40 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="py-3 px-4">Mã job</th>
                  <th className="py-3 px-4">Loại tác vụ</th>
                  <th className="py-3 px-4">Trạng thái</th>
                  <th className="py-3 px-4 min-w-[160px]">Tiến độ</th>
                  <th className="py-3 px-4">Thử lại</th>
                  <th className="py-3 px-4">Thời gian</th>
                  <th className="py-3 px-4 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filteredJobs.map((job) => (
                  <tr key={job.id} className="hover:bg-surface-raised/30 transition">
                    <td className="py-3 px-4 font-mono font-medium text-purple-400">{job.id}</td>
                    <td className="py-3 px-4 font-mono text-gray-300">{job.type}</td>
                    <td className="py-3 px-4">{getStatusBadge(job.status)}</td>
                    <td className="py-3 px-4">
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs text-gray-400">
                          <span>{Math.round(job.progress * 100)}%</span>
                        </div>
                        <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-primary h-full transition-all duration-300 rounded-full"
                            style={{ width: `${Math.round(job.progress * 100)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-xs text-gray-400">
                      {job.attempts} / {job.max_attempts}
                    </td>
                    <td className="py-3 px-4 text-xs text-gray-400">
                      {new Date(job.created_at).toLocaleTimeString("vi-VN")}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <button
                        onClick={() => handleOpenLog(job)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-surface-raised hover:bg-gray-700 text-gray-300 rounded border border-border transition"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        Log
                      </button>

                      {job.status === "failed" || job.status === "cancelled" ? (
                        <button
                          onClick={() => retryMutation.mutate(job.id)}
                          disabled={retryMutation.isPending}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 rounded border border-purple-500/30 transition"
                        >
                          <RotateCw className="w-3.5 h-3.5" />
                          Thử lại
                        </button>
                      ) : null}

                      {job.status === "queued" || job.status === "running" ? (
                        <button
                          onClick={() => cancelMutation.mutate(job.id)}
                          disabled={cancelMutation.isPending}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 rounded border border-rose-500/30 transition"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          Hủy
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Log Modal */}
      {selectedLogJob && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl w-full max-w-3xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between p-4 border-b border-border bg-surface-raised/40">
              <div className="flex items-center gap-2 font-mono">
                <FileText className="w-4 h-4 text-purple-400" />
                <span className="font-semibold text-gray-200">Log: {selectedLogJob.id}</span>
                <span className="text-xs text-gray-400">({selectedLogJob.type})</span>
              </div>
              <button
                onClick={() => setSelectedLogJob(null)}
                className="text-gray-400 hover:text-white p-1 rounded transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 font-mono text-xs bg-background text-gray-300 space-y-1">
              {isLoadingLog ? (
                <div className="text-gray-400">Đang đọc file log...</div>
              ) : logContent ? (
                <pre className="whitespace-pre-wrap">{logContent}</pre>
              ) : (
                <div className="text-gray-500 italic">Chưa có thông tin log ghi nhận.</div>
              )}
            </div>

            <div className="p-3 border-t border-border bg-surface-raised/20 flex justify-end">
              <button
                onClick={() => setSelectedLogJob(null)}
                className="px-4 py-1.5 text-xs font-medium bg-surface-raised hover:bg-gray-700 text-gray-300 rounded-lg border border-border transition"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
