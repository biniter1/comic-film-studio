import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useEvents } from "../api/events";
import { api } from "../api/client";
import {
  FolderKanban,
  Upload,
  Scissors,
  ScrollText,
  LayoutGrid,
  Clock,
  MessageSquare,
  PackageCheck,
  Activity,
  Settings,
  Film,
  Radio,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "/projects", label: "Dự án", icon: FolderKanban },
  { to: "/import", label: "Nhập chapter", icon: Upload },
  { to: "/frames", label: "Khung", icon: Scissors },
  { to: "/script", label: "Kịch bản", icon: ScrollText },
  { to: "/shot-board", label: "Bảng shot", icon: LayoutGrid },
  { to: "/queue", label: "Hàng chờ", icon: Clock },
  { to: "/dialogue", label: "Thoại", icon: MessageSquare },
  { to: "/export", label: "Xuất", icon: PackageCheck },
  { to: "/jobs", label: "Job", icon: Activity },
  { to: "/settings", label: "Cài đặt", icon: Settings },
];

const ACTIVE =
  "flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-medium transition bg-primary text-white shadow-sm";
const IDLE =
  "flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-medium transition text-gray-400 hover:text-gray-200 hover:bg-surface-raised/60";

/** Chapter screens live under /chapters/:cid/{import,frames}; keep their nav item highlighted. */
function navActive(to: string, isActive: boolean, path: string): boolean {
  if (to === "/import") return isActive || /^\/chapters\/[^/]+\/import/.test(path);
  if (to === "/frames") return isActive || /^\/chapters\/[^/]+\/frames/.test(path);
  return isActive;
}

export function AppShell() {
  const location = useLocation();
  const { isConnected } = useEvents();

  const { data: jobs = [] } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.getJobs(),
    refetchInterval: 10000,
  });

  const runningCount = jobs.filter((j) => j.status === "running").length;
  const failedCount = jobs.filter((j) => j.status === "failed").length;

  return (
    <div className="flex h-screen bg-background text-gray-200 overflow-hidden font-sans">
      {/* Sidebar */}
      <aside className="w-64 bg-surface border-r border-border flex flex-col justify-between shrink-0">
        <div>
          {/* Logo */}
          <div className="h-16 px-5 border-b border-border flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/20 border border-primary/40 flex items-center justify-center text-primary">
              <Film className="w-5 h-5" />
            </div>
            <div>
              <div className="font-bold text-sm tracking-wide text-white">Comic Film Studio</div>
              <div className="text-[10px] text-gray-400 font-mono">v0.1 • Localhost</div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="p-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    navActive(item.to, isActive, location.pathname) ? ACTIVE : IDLE
                  }
                >
                  <Icon className="w-4 h-4" />
                  <span>{item.label}</span>
                  {item.to === "/jobs" && runningCount > 0 && (
                    <span className="ml-auto px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-500 text-white animate-pulse">
                      {runningCount}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Workspace info */}
        <div className="p-4 border-t border-border/80 text-xs text-gray-500 font-mono">
          <div>Windows 11 Local</div>
          <div>Port: 8765</div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <main className="flex-1 overflow-y-auto bg-background">
          <Outlet />
        </main>

        {/* Bottom Status Bar */}
        <footer className="h-9 px-5 bg-surface border-t border-border flex items-center justify-between text-xs text-gray-400 shrink-0">
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-1.5">
              <Radio
                className={`w-3.5 h-3.5 ${
                  isConnected ? "text-emerald-400 animate-pulse" : "text-gray-500"
                }`}
              />
              <span>{isConnected ? "SSE: Đã kết nối" : "SSE: Đang kết nối..."}</span>
            </div>

            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              <span>Đang chạy: <strong className="text-gray-200">{runningCount}</strong></span>
            </div>

            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-rose-400" />
              <span>Lỗi: <strong className="text-gray-200">{failedCount}</strong></span>
            </div>
          </div>

          <div className="font-mono text-[11px] text-gray-500">
            http://127.0.0.1:8765
          </div>
        </footer>
      </div>
    </div>
  );
}
