import React, { useEffect, useState } from "react";
import { getEodRefreshStatus, getExperimentManifest, getStocks } from "@/lib/data";
import {
  Briefcase,
  CandlestickChart,
  Database,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";

export type PageId =
  | "command-center"
  | "trade-plan"
  | "final-portfolio"
  | "stock-inspector"
  | "performance-trust"
  | "advanced"
  | "admin-status";

interface LayoutProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  children: React.ReactNode;
}

const NAV_ITEMS: { id: PageId; label: string; icon: React.ReactNode }[] = [
  { id: "command-center", label: "Command Center", icon: <LayoutDashboard className="w-4 h-4" /> },
  { id: "trade-plan", label: "Trade Plan", icon: <CandlestickChart className="w-4 h-4" /> },
  { id: "final-portfolio", label: "Final Portfolio", icon: <Briefcase className="w-4 h-4" /> },
  { id: "stock-inspector", label: "Stock Inspector", icon: <Search className="w-4 h-4" /> },
  { id: "performance-trust", label: "Performance & Trust", icon: <ShieldCheck className="w-4 h-4" /> },
  { id: "advanced", label: "Advanced Research", icon: <SlidersHorizontal className="w-4 h-4" /> },
  { id: "admin-status", label: "Admin Status", icon: <Settings className="w-4 h-4" /> },
];

function DataAsOf() {
  const eod = getEodRefreshStatus();
  const manifest = getExperimentManifest();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  const measured = manifest?.data_freshness?.eod?.latest_date ?? null;
  const asOf = measured || eod.resolved_date || eod.requested_date;
  const ok = eod.status === "ok";

  const daysBehind = (() => {
    if (!asOf) return null;
    const have = new Date(asOf + "T00:00:00");
    if (Number.isNaN(have.getTime())) return null;
    const todayUtc = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.floor((todayUtc - have.getTime()) / 86_400_000);
  })();

  const stale = daysBehind !== null && daysBehind > 4;
  const behind = !ok || (daysBehind !== null && daysBehind > 1);
  const dot = !ok || stale ? "bg-red-500" : behind ? "bg-amber-500" : "bg-emerald-500";
  const title = !ok
    ? `Last EOD refresh ${eod.status}`
    : stale
      ? `NSE EOD data as of ${asOf} - ${daysBehind} days old. The daily refresh is not keeping up.`
      : daysBehind !== null && daysBehind > 1
        ? `NSE EOD data as of ${asOf} - ${daysBehind} days old.`
        : `NSE EOD data as of ${asOf}`;

  return (
    <div className="flex flex-col items-end leading-tight" title={title}>
      <span className="flex items-center gap-1.5 text-xs text-slate-600">
        <span className={`w-2 h-2 rounded-full ${dot}`} />
        {asOf ? `Data as of ${asOf}` : "Data date unknown"}
        {stale && <span className="text-[10px] font-medium text-red-600">stale</span>}
      </span>
      <span className="text-[10px] text-slate-400 tabular-nums">
        {now.toLocaleString(undefined, {
          year: "numeric",
          month: "short",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
    </div>
  );
}

export function Layout({ currentPage, onNavigate, children }: LayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const stockCount = getStocks().length;

  const handleNav = (page: PageId) => {
    onNavigate(page);
    setMobileOpen(false);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex">
      <aside className="hidden lg:flex w-60 flex-col bg-slate-900 text-slate-300 fixed h-screen z-30">
        <SidebarContent currentPage={currentPage} onNavigate={handleNav} stockCount={stockCount} />
      </aside>

      {mobileOpen && (
        <>
          <div
            className="lg:hidden fixed inset-0 bg-black/50 z-40"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="lg:hidden w-60 flex-col bg-slate-900 text-slate-300 fixed h-screen z-50 flex">
            <SidebarContent currentPage={currentPage} onNavigate={handleNav} stockCount={stockCount} />
          </aside>
        </>
      )}

      <div className="flex-1 lg:ml-60 flex flex-col min-h-screen">
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
                <h1 className="text-sm font-bold text-slate-900">Indian Factor Intelligence</h1>
                <p className="text-[10px] text-slate-500">Nifty 200 Trading Assistant</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500 hidden sm:block">Monthly Positional Model</span>
            <DataAsOf />
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-8 overflow-x-hidden">{children}</main>

        <footer className="px-4 lg:px-8 py-4 border-t border-slate-200 bg-white">
          <p className="text-xs text-slate-400 text-center">
            Indian Regime/Factor/Portfolio Intelligence Dashboard - Nifty 200 Universe ({stockCount} Stocks) -
            Monthly model + daily execution overlay
          </p>
        </footer>
      </div>
    </div>
  );
}

function SidebarContent({
  currentPage,
  onNavigate,
  stockCount,
}: {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  stockCount: number;
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
            <p className="text-[10px] text-slate-400">Trading Assistant</p>
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
          <p>Universe: Nifty 200 ({stockCount} stocks)</p>
          <p>Mode: Monthly + EOD overlay</p>
          <p>Data: Indian SQLite/CSV</p>
        </div>
      </div>
    </>
  );
}
