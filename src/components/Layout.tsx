import React, { useState } from "react";
import {
  LayoutDashboard,
  Gauge,
  Layers,
  PieChart,
  Briefcase,
  CandlestickChart,
  TrendingUp,
  Newspaper,
  PlayCircle,
  GitBranch,
  Database,
  Menu,
  X,
} from "lucide-react";

export type PageId =
  | "overview"
  | "regime"
  | "factors"
  | "allocation"
  | "portfolio"
  | "signals"
  | "backtest"
  | "news"
  | "simulation"
  | "model-report";

interface LayoutProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  children: React.ReactNode;
}

const NAV_ITEMS: { id: PageId; label: string; icon: React.ReactNode }[] = [
  { id: "overview", label: "Overview", icon: <LayoutDashboard className="w-4 h-4" /> },
  { id: "regime", label: "Regime Dashboard", icon: <Gauge className="w-4 h-4" /> },
  { id: "factors", label: "Factor Dashboard", icon: <Layers className="w-4 h-4" /> },
  { id: "allocation", label: "Allocation", icon: <PieChart className="w-4 h-4" /> },
  { id: "portfolio", label: "Portfolio", icon: <Briefcase className="w-4 h-4" /> },
  { id: "signals", label: "Stock Signals", icon: <CandlestickChart className="w-4 h-4" /> },
  { id: "backtest", label: "Backtest", icon: <TrendingUp className="w-4 h-4" /> },
  { id: "news", label: "News", icon: <Newspaper className="w-4 h-4" /> },
  { id: "simulation", label: "Simulation", icon: <PlayCircle className="w-4 h-4" /> },
  { id: "model-report", label: "Model Report", icon: <GitBranch className="w-4 h-4" /> },
];

export function Layout({ currentPage, onNavigate, children }: LayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleNav = (page: PageId) => {
    onNavigate(page);
    setMobileOpen(false);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Sidebar - Desktop */}
      <aside className="hidden lg:flex w-60 flex-col bg-slate-900 text-slate-300 fixed h-screen z-30">
        <SidebarContent currentPage={currentPage} onNavigate={handleNav} />
      </aside>

      {/* Sidebar - Mobile */}
      {mobileOpen && (
        <>
          <div
            className="lg:hidden fixed inset-0 bg-black/50 z-40"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="lg:hidden w-60 flex-col bg-slate-900 text-slate-300 fixed h-screen z-50 flex">
            <SidebarContent currentPage={currentPage} onNavigate={handleNav} />
          </aside>
        </>
      )}

      {/* Main Content */}
      <div className="flex-1 lg:ml-60 flex flex-col min-h-screen">
        {/* Top Bar */}
        <header className="bg-white border-b border-slate-200 px-4 lg:px-8 py-3 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <button
              className="lg:hidden p-1.5 rounded-md hover:bg-slate-100"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="w-5 h-5 text-slate-700" />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center">
                <Database className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-slate-900">
                  Indian Factor Intelligence
                </h1>
                <p className="text-[10px] text-slate-500">
                  Nifty 200 Regime & Portfolio Dashboard
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500 hidden sm:block">
              Monthly Positional Model
            </span>
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 lg:p-8 overflow-x-hidden">{children}</main>

        {/* Footer */}
        <footer className="px-4 lg:px-8 py-4 border-t border-slate-200 bg-white">
          <p className="text-xs text-slate-400 text-center">
            Indian Regime/Factor/Portfolio Intelligence Dashboard — Nifty 200
            Universe (189 Stocks) — GMM-5 Regime Model
          </p>
        </footer>
      </div>
    </div>
  );
}

function SidebarContent({
  currentPage,
  onNavigate,
}: {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
}) {
  return (
    <>
      <div className="px-5 py-5 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
            <Database className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-white">Factor Intel</p>
            <p className="text-[10px] text-slate-400">India Nifty 200</p>
          </div>
        </div>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              currentPage === item.id
                ? "bg-blue-600 text-white"
                : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-slate-800">
        <div className="text-[10px] text-slate-500 space-y-1">
          <p>Universe: Nifty 200 (189 stocks)</p>
          <p>Model: GMM-5 + Grid Search</p>
          <p>Data: Indian SQLite/CSV</p>
        </div>
      </div>
    </>
  );
}




