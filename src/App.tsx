import { useEffect, useState } from "react";
import { Layout, type PageId } from "@/components/Layout";
import { OverviewPage } from "@/pages/OverviewPage";
import { RegimePage } from "@/pages/RegimePage";
import { FactorPage } from "@/pages/FactorPage";
import { AllocationPage } from "@/pages/AllocationPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { SignalsPage } from "@/pages/SignalsPage";
import { BacktestPage } from "@/pages/BacktestPage";
import { NewsPage } from "@/pages/NewsPage";
import { SimulationPage } from "@/pages/SimulationPage";
import { ModelReportPage } from "@/pages/ModelReportPage";
import { loadDashboardData } from "@/lib/data";

function App() {
  const [page, setPage] = useState<PageId>("overview");
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadDashboardData()
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <div className="max-w-lg rounded-xl border border-red-200 bg-white p-6 shadow-sm">
          <h1 className="text-lg font-bold text-red-700">Dashboard data failed to load</h1>
          <p className="mt-2 text-sm text-slate-600">{loadError}</p>
          <p className="mt-4 text-xs text-slate-500">Run the pipeline or check that JSON files exist under public/data.</p>
        </div>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin" />
          <h1 className="text-sm font-semibold text-slate-900">Loading Indian Factor Intelligence data</h1>
          <p className="mt-1 text-xs text-slate-500">Fetching dashboard JSON snapshots...</p>
        </div>
      </div>
    );
  }

  return (
    <Layout currentPage={page} onNavigate={setPage}>
      {page === "overview" && <OverviewPage />}
      {page === "regime" && <RegimePage />}
      {page === "factors" && <FactorPage />}
      {page === "allocation" && <AllocationPage />}
      {page === "portfolio" && <PortfolioPage />}
      {page === "signals" && <SignalsPage />}
      {page === "backtest" && <BacktestPage />}
      {page === "news" && <NewsPage />}
      {page === "simulation" && <SimulationPage />}
      {page === "model-report" && <ModelReportPage />}
    </Layout>
  );
}

export default App;


