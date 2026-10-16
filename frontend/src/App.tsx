import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./layout/AppShell";
import { JobsPage } from "./pages/JobsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<Navigate to="/jobs" replace />} />
            <Route
              path="projects"
              element={
                <PlaceholderPage
                  title="Dự án"
                  phase="Phase 1"
                  description="Quản lý danh sách dự án, chapter và tiến độ tổng quan"
                />
              }
            />
            <Route
              path="import"
              element={
                <PlaceholderPage
                  title="Nhập chapter"
                  phase="Phase 1"
                  description="Tải ảnh từ URL hoặc kéo thả thư mục ảnh truyện tranh"
                />
              }
            />
            <Route
              path="frames"
              element={
                <PlaceholderPage
                  title="Khung tranh"
                  phase="Phase 1"
                  description="Ghép dải dọc, cắt khung tự động và chỉnh tay gộp/tách khung"
                />
              }
            />
            <Route
              path="script"
              element={
                <PlaceholderPage
                  title="Kịch bản & Story Bible"
                  phase="Phase 2"
                  description="Hồ sơ nhân vật, chiêu thức võ công và phân cảnh AI"
                />
              }
            />
            <Route
              path="shot-board"
              element={
                <PlaceholderPage
                  title="Bảng shot"
                  phase="Phase 2"
                  description="Toàn cảnh các chuỗi shot (chains), trạng thái và quy tắc chuyển cảnh"
                />
              }
            />
            <Route
              path="queue"
              element={
                <PlaceholderPage
                  title="Hàng chờ thủ công"
                  phase="Phase 3"
                  description="Bàn giao thủ công Nano Banana (keyframe) và Muse (video)"
                />
              }
            />
            <Route
              path="dialogue"
              element={
                <PlaceholderPage
                  title="Thoại & TTS"
                  phase="Phase 4"
                  description="Danh sách câu thoại, tạo giọng nhân vật và kiểm tra audio"
                />
              }
            />
            <Route
              path="export"
              element={
                <PlaceholderPage
                  title="Xuất gói CapCut"
                  phase="Phase 4"
                  description="Đóng gói video đã duyệt, phụ đề srt và bảng shot sheet hoàn chỉnh"
                />
              }
            />
            <Route path="jobs" element={<JobsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/jobs" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
