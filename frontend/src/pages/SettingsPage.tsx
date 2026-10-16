import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Settings, CheckCircle2, AlertTriangle, Save, KeyRound, HardDrive, Cpu, Video } from "lucide-react";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [geminiKeyInput, setGeminiKeyInput] = useState("");
  const [concurrency, setConcurrency] = useState<number>(2);
  const [maxTabs, setMaxTabs] = useState<number>(4);
  const [clipSeconds, setClipSeconds] = useState<number>(4.0);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const { data: providerStatus } = useQuery({
    queryKey: ["providers-status"],
    queryFn: () => api.getProvidersStatus(),
  });

  useEffect(() => {
    if (settings) {
      setConcurrency(settings.job_concurrency);
      setMaxTabs(settings.max_parallel_muse_tabs);
      setClipSeconds(settings.muse_clip_seconds);
    }
  }, [settings]);

  const updateMutation = useMutation({
    mutationFn: () =>
      api.updateSettings({
        job_concurrency: concurrency,
        max_parallel_muse_tabs: maxTabs,
        muse_clip_seconds: clipSeconds,
        ...(geminiKeyInput.trim() ? { gemini_api_key: geminiKeyInput.trim() } : {}),
      }),
    onSuccess: () => {
      setGeminiKeyInput("");
      setSaveSuccess(true);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["providers-status"] });
      setTimeout(() => setSaveSuccess(false), 3000);
    },
  });

  if (isLoading || !settings) {
    return <div className="p-8 text-gray-400">Đang tải cấu hình hệ thống...</div>;
  }

  const isGeminiConfigured = providerStatus?.providers.gemini.configured ?? settings.gemini_configured;
  const isFfmpegAvailable = providerStatus?.tools.ffmpeg.available ?? settings.ffmpeg_available;
  const ffmpegVersion = providerStatus?.tools.ffmpeg.version ?? settings.ffmpeg_version;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100 flex items-center gap-2">
          <Settings className="w-6 h-6 text-purple-400" />
          Cài đặt hệ thống
        </h1>
        <p className="text-sm text-gray-400 mt-1">
          Cấu hình môi trường lưu trữ, kết nối AI và các thông số chạy nền
        </p>
      </div>

      {saveSuccess && (
        <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          Đã lưu cài đặt thành công!
        </div>
      )}

      {/* Storage and System Paths */}
      <div className="bg-surface border border-border rounded-xl p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-200 flex items-center gap-2">
          <HardDrive className="w-5 h-5 text-gray-400" />
          Thư mục dữ liệu (data_dir)
        </h2>
        <p className="text-xs text-gray-400">
          Nơi lưu trữ file cơ sở dữ liệu SQLite, file log, các chapter và media.
        </p>
        <div className="bg-background border border-border rounded-lg p-3 font-mono text-sm text-purple-300">
          {settings.data_dir}
        </div>
      </div>

      {/* Provider Status */}
      <div className="bg-surface border border-border rounded-xl p-6 space-y-6">
        <h2 className="text-base font-semibold text-gray-200 flex items-center gap-2">
          <KeyRound className="w-5 h-5 text-gray-400" />
          Kết nối AI Provider
        </h2>

        {/* Gemini */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-medium text-sm text-gray-200">Google Gemini API</span>
              <p className="text-xs text-gray-400">Dùng cho phân tích kịch bản, trích khung và tạo prompt</p>
            </div>
            {isGeminiConfigured ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Đã cấu hình
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                <AlertTriangle className="w-3.5 h-3.5" />
                Chưa cấu hình
              </span>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400">
              {isGeminiConfigured ? "Cập nhật API Key mới (để trống nếu không đổi)" : "Nhập Gemini API Key:"}
            </label>
            <input
              type="password"
              value={geminiKeyInput}
              onChange={(e) => setGeminiKeyInput(e.target.value)}
              placeholder="AIzaSy..."
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
            />
            <p className="text-xs text-gray-500 italic">
              * Khóa API được lưu độc quyền vào <code>secrets.env</code> trong thư mục dữ liệu và không bao giờ hiển thị lại trên giao diện.
            </p>
          </div>
        </div>
      </div>

      {/* System Tools Check */}
      <div className="bg-surface border border-border rounded-xl p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-200 flex items-center gap-2">
          <Video className="w-5 h-5 text-gray-400" />
          Công cụ đa phương tiện (ffmpeg)
        </h2>

        <div className="flex items-center justify-between">
          <div>
            <span className="font-medium text-sm text-gray-200">ffmpeg / ffprobe</span>
            <p className="text-xs text-gray-400">Dùng để trích khung cuối video take và kiểm tra thông số media</p>
          </div>
          {isFfmpegAvailable ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Đã sẵn sàng
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <AlertTriangle className="w-3.5 h-3.5" />
              Chưa cài đặt
            </span>
          )}
        </div>

        {isFfmpegAvailable ? (
          <div className="text-xs text-gray-400 font-mono bg-background p-2.5 rounded border border-border">
            {ffmpegVersion}
          </div>
        ) : (
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs text-amber-300">
            Cảnh báo: Không tìm thấy lệnh <code>ffmpeg</code> trong PATH hệ thống. Hãy cài đặt ffmpeg và thêm vào biến môi trường PATH để trích xuất khung hình ở các phase sau.
          </div>
        )}
      </div>

      {/* Execution Parameters */}
      <div className="bg-surface border border-border rounded-xl p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-200 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-gray-400" />
          Tham số thực thi tác vụ
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-1">
            <label className="text-xs text-gray-400">Số job chạy đồng thời (concurrency)</label>
            <input
              type="number"
              min={1}
              max={10}
              value={concurrency}
              onChange={(e) => setConcurrency(Number(e.target.value))}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-primary"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400">Số tab Muse song song tối đa</label>
            <input
              type="number"
              min={1}
              max={16}
              value={maxTabs}
              onChange={(e) => setMaxTabs(Number(e.target.value))}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-primary"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400">Độ dài clip Muse dự kiến (giây)</label>
            <input
              type="number"
              step={0.5}
              min={1}
              value={clipSeconds}
              onChange={(e) => setClipSeconds(Number(e.target.value))}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-primary"
            />
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={() => updateMutation.mutate()}
          disabled={updateMutation.isPending}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {updateMutation.isPending ? "Đang lưu..." : "Lưu cài đặt"}
        </button>
      </div>
    </div>
  );
}
