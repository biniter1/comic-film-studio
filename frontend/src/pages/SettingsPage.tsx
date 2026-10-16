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

  const [provider, setProvider] = useState<"gemini" | "openai_compat">("gemini");
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("https://revidapi.com/v1");
  const [openaiAuthHeader, setOpenaiAuthHeader] = useState<"x-api-key" | "authorization-bearer">("x-api-key");
  const [openaiKeyInput, setOpenaiKeyInput] = useState("");
  const [openaiKeyMsg, setOpenaiKeyMsg] = useState<{ ok: boolean; text: string } | null>(null);

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
      setProvider(settings.analysis_provider || "gemini");
      setOpenaiBaseUrl(settings.openai_base_url || "https://revidapi.com/v1");
      setOpenaiAuthHeader(settings.openai_auth_header || "x-api-key");
    }
  }, [settings]);

  const [keyMsg, setKeyMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const refreshStatus = () => {
    queryClient.invalidateQueries({ queryKey: ["settings"] });
    queryClient.invalidateQueries({ queryKey: ["providers-status"] });
  };
  const testKey = useMutation({
    mutationFn: () => api.testGeminiKey(),
    onSuccess: (r) => setKeyMsg({ ok: r.ok, text: r.message_vi }),
    onError: (e: unknown) => setKeyMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }),
  });
  const saveKey = useMutation({
    mutationFn: () => api.saveGeminiKey(geminiKeyInput.trim()),
    onSuccess: () => {
      setGeminiKeyInput("");
      setKeyMsg({ ok: true, text: "Đã lưu API key. Đang kiểm tra kết nối…" });
      refreshStatus();
      testKey.mutate();
    },
    onError: (e: unknown) => setKeyMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }),
  });
  const deleteKey = useMutation({
    mutationFn: () => api.deleteGeminiKey(),
    onSuccess: () => {
      setKeyMsg({ ok: true, text: "Đã xóa API key." });
      refreshStatus();
    },
  });

  const testOpenAIKey = useMutation({
    mutationFn: () => api.testOpenAIKey(),
    onSuccess: (r) => setOpenaiKeyMsg({ ok: r.ok, text: r.message_vi }),
    onError: (e: unknown) => setOpenaiKeyMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }),
  });
  const saveOpenAIKey = useMutation({
    mutationFn: () => api.saveOpenAIKey(openaiKeyInput.trim()),
    onSuccess: () => {
      setOpenaiKeyInput("");
      setOpenaiKeyMsg({ ok: true, text: "Đã lưu API key. Đang kiểm tra kết nối…" });
      refreshStatus();
      testOpenAIKey.mutate();
    },
    onError: (e: unknown) => setOpenaiKeyMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }),
  });
  const deleteOpenAIKey = useMutation({
    mutationFn: () => api.deleteOpenAIKey(),
    onSuccess: () => {
      setOpenaiKeyMsg({ ok: true, text: "Đã xóa API key." });
      refreshStatus();
    },
  });
  const changeProviderMutation = useMutation({
    mutationFn: (p: "gemini" | "openai_compat") => api.updateSettings({ analysis_provider: p }),
    onSuccess: () => {
      refreshStatus();
    },
  });
  const updateOpenAISettingsMutation = useMutation({
    mutationFn: (params: { openai_base_url?: string; openai_auth_header?: "x-api-key" | "authorization-bearer" }) =>
      api.updateSettings(params),
    onSuccess: () => {
      refreshStatus();
    },
  });


  const updateMutation = useMutation({
    mutationFn: () =>
      api.updateSettings({
        job_concurrency: concurrency,
        max_parallel_muse_tabs: maxTabs,
        muse_clip_seconds: clipSeconds,
      }),
    onSuccess: () => {
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
  const isOpenAIConfigured =
    providerStatus?.providers.openai_compat?.configured ?? settings.openai_configured;
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

        {/* Provider Switcher */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Chọn nhà cung cấp AI phân tích:
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              type="button"
              data-testid="provider-gemini-btn"
              onClick={() => {
                setProvider("gemini");
                changeProviderMutation.mutate("gemini");
              }}
              className={`p-3 rounded-lg border text-left transition-all ${
                provider === "gemini"
                  ? "border-primary bg-primary/10 text-white"
                  : "border-border bg-background text-gray-400 hover:text-gray-200"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm">Gemini chính hãng</span>
                {isGeminiConfigured && (
                  <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full">
                    Đã lưu key
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-1">Google AI Studio API chính hãng (mặc định)</p>
            </button>

            <button
              type="button"
              data-testid="provider-openai-btn"
              onClick={() => {
                setProvider("openai_compat");
                changeProviderMutation.mutate("openai_compat");
              }}
              className={`p-3 rounded-lg border text-left transition-all ${
                provider === "openai_compat"
                  ? "border-primary bg-primary/10 text-white"
                  : "border-border bg-background text-gray-400 hover:text-gray-200"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm">Cổng tương thích OpenAI</span>
                {isOpenAIConfigured && (
                  <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full">
                    Đã lưu key
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-1">revidapi.com, vLLM, OpenRouter hoặc cổng tự dựng</p>
            </button>
          </div>
        </div>

        {/* Gemini */}
        {provider === "gemini" && (
          <div className="space-y-3 pt-2 border-t border-border/50">
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

            <form
              className="space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (geminiKeyInput.trim()) saveKey.mutate();
              }}
            >
              <label className="text-xs text-gray-400">
                {isGeminiConfigured
                  ? `Đang dùng key ${settings.gemini_key_hint ?? ""} — dán key mới để thay`
                  : "Dán Gemini API Key (lấy ở aistudio.google.com → Get API key):"}
              </label>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={geminiKeyInput}
                  onChange={(e) => setGeminiKeyInput(e.target.value)}
                  placeholder="AIzaSy…"
                  autoComplete="off"
                  className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
                />
                <button
                  type="submit"
                  disabled={!geminiKeyInput.trim() || saveKey.isPending}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium disabled:opacity-40"
                >
                  <KeyRound className="w-4 h-4" /> {saveKey.isPending ? "Đang lưu…" : "Lưu key"}
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={!isGeminiConfigured || testKey.isPending}
                  onClick={() => testKey.mutate()}
                  className="px-3 py-1.5 rounded-lg text-xs border border-border bg-surface-raised text-gray-200 hover:bg-gray-700 disabled:opacity-40"
                >
                  {testKey.isPending ? "Đang kiểm tra…" : "Kiểm tra kết nối"}
                </button>
                {isGeminiConfigured && (
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm("Xóa API key Gemini khỏi máy?")) deleteKey.mutate();
                    }}
                    className="px-3 py-1.5 rounded-lg text-xs border border-red-900 bg-red-950/40 text-red-200 hover:bg-red-900/60"
                  >
                    Xóa key
                  </button>
                )}
                {keyMsg && (
                  <span
                    data-testid="key-msg"
                    className={`text-xs ${keyMsg.ok ? "text-emerald-400" : "text-red-300"}`}
                  >
                    {keyMsg.ok ? "✓ " : "✗ "}
                    {keyMsg.text}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 italic">
                Key chỉ lưu trong <code>secrets.env</code> ở thư mục dữ liệu trên máy bạn, không bao giờ hiển thị lại.
              </p>
            </form>
          </div>
        )}

        {/* OpenAI Compat */}
        {provider === "openai_compat" && (
          <div className="space-y-4 pt-2 border-t border-border/50">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium text-sm text-gray-200">Cổng tương thích OpenAI</span>
                <p className="text-xs text-gray-400">Dùng cho các cổng như revidapi.com, OpenRouter hoặc self-hosted</p>
              </div>
              {isOpenAIConfigured ? (
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

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Base URL (cổng API):</label>
                <input
                  type="text"
                  value={openaiBaseUrl}
                  onChange={(e) => setOpenaiBaseUrl(e.target.value)}
                  onBlur={() => updateOpenAISettingsMutation.mutate({ openai_base_url: openaiBaseUrl.trim() })}
                  placeholder="https://revidapi.com/v1"
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400 block mb-1">Kiểu Header xác thực:</label>
                <select
                  value={openaiAuthHeader}
                  onChange={(e) => {
                    const val = e.target.value as "x-api-key" | "authorization-bearer";
                    setOpenaiAuthHeader(val);
                    updateOpenAISettingsMutation.mutate({ openai_auth_header: val });
                  }}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-primary"
                >
                  <option value="x-api-key">x-api-key (mặc định revidapi.com)</option>
                  <option value="authorization-bearer">Authorization: Bearer &lt;key&gt;</option>
                </select>
              </div>
            </div>

            <form
              className="space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (openaiKeyInput.trim()) saveOpenAIKey.mutate();
              }}
            >
              <label className="text-xs text-gray-400">
                {isOpenAIConfigured
                  ? `Đang dùng key ${settings.openai_key_hint ?? ""} — dán key mới để thay`
                  : "Dán API Key cổng tương thích OpenAI:"}
              </label>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={openaiKeyInput}
                  onChange={(e) => setOpenaiKeyInput(e.target.value)}
                  placeholder="sk-…"
                  autoComplete="off"
                  className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
                />
                <button
                  type="submit"
                  disabled={!openaiKeyInput.trim() || saveOpenAIKey.isPending}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium disabled:opacity-40"
                >
                  <KeyRound className="w-4 h-4" /> {saveOpenAIKey.isPending ? "Đang lưu…" : "Lưu key"}
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={!isOpenAIConfigured || testOpenAIKey.isPending}
                  onClick={() => testOpenAIKey.mutate()}
                  className="px-3 py-1.5 rounded-lg text-xs border border-border bg-surface-raised text-gray-200 hover:bg-gray-700 disabled:opacity-40"
                >
                  {testOpenAIKey.isPending ? "Đang kiểm tra…" : "Kiểm tra kết nối"}
                </button>
                {isOpenAIConfigured && (
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm("Xóa API key OpenAI Compat khỏi máy?")) deleteOpenAIKey.mutate();
                    }}
                    className="px-3 py-1.5 rounded-lg text-xs border border-red-900 bg-red-950/40 text-red-200 hover:bg-red-900/60"
                  >
                    Xóa key
                  </button>
                )}
                {openaiKeyMsg && (
                  <span
                    data-testid="openai-key-msg"
                    className={`text-xs ${openaiKeyMsg.ok ? "text-emerald-400" : "text-red-300"}`}
                  >
                    {openaiKeyMsg.ok ? "✓ " : "✗ "}
                    {openaiKeyMsg.text}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 italic">
                Key chỉ lưu trong <code>secrets.env</code> ở thư mục dữ liệu trên máy bạn, không bao giờ hiển thị lại.
              </p>
            </form>
          </div>
        )}
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
      <div className="flex justify-end items-center gap-3">
        {saveSuccess && <span className="text-xs text-emerald-400">✓ Đã lưu (giữ nguyên sau khi khởi động lại)</span>}
        <button
          onClick={() => updateMutation.mutate()}
          disabled={updateMutation.isPending}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {updateMutation.isPending ? "Đang lưu..." : "Lưu tham số"}
        </button>
      </div>
    </div>
  );
}
