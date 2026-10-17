import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./layout/AppShell";
import { JobsPage } from "./pages/JobsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { ProjectDetailPage, ProjectsPage } from "./pages/ProjectsPage";
import { ImportPage } from "./pages/ImportPage";
import { FramesPage } from "./pages/FramesPage";
import { DialoguePage } from "./pages/DialoguePage";
import { GlossaryPage } from "./pages/GlossaryPage";
import { ShotBoardPage } from "./pages/ShotBoardPage";
import { lastChapter } from "./api/studio";

/** Sidebar shortcuts open the last chapter you worked on (or the project list). */
function LastChapter({ to }: { to: "import" | "frames" | "dialogue" | "shots" }) {
  const cid = lastChapter();
  return <Navigate to={cid ? `/chapters/${cid}/${to}` : "/projects"} replace />;
}

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
            <Route index element={<Navigate to="/projects" replace />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="projects/:pid" element={<ProjectDetailPage />} />
            <Route path="chapters/:cid/import" element={<ImportPage />} />
            <Route path="chapters/:cid/frames" element={<FramesPage />} />
            <Route path="import" element={<LastChapter to="import" />} />
            <Route path="frames" element={<LastChapter to="frames" />} />
            <Route path="chapters/:cid/dialogue" element={<DialoguePage />} />
            <Route path="projects/:pid/glossary" element={<GlossaryPage />} />
            <Route path="script" element={<LastChapter to="dialogue" />} />
            <Route path="chapters/:cid/shots" element={<ShotBoardPage />} />
            <Route path="shot-board" element={<LastChapter to="shots" />} />
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
            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
