import { useState } from "react";
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

function App() {
  const [page, setPage] = useState<PageId>("overview");

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


