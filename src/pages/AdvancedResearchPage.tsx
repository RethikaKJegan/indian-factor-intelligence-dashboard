import { useState } from "react";
import { AllocationPage } from "@/pages/AllocationPage";
import { BacktestPage } from "@/pages/BacktestPage";
import { FactorPage } from "@/pages/FactorPage";
import { ModelReportPage } from "@/pages/ModelReportPage";
import { NewsPage } from "@/pages/NewsPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { RegimePage } from "@/pages/RegimePage";
import { SignalsPage } from "@/pages/SignalsPage";
import { SimulationPage } from "@/pages/SimulationPage";

const sections = [
  "Overview",
  "Regime",
  "Factors",
  "Allocation",
  "Portfolio Signals",
  "Backtest",
  "News",
  "Simulation",
  "Model Report",
] as const;

type Section = (typeof sections)[number];

export function AdvancedResearchPage() {
  const [section, setSection] = useState<Section>("Overview");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Advanced Research</h2>
        <p className="mt-1 text-sm text-slate-500">
          Original quant-heavy dashboards are kept here for research and review.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {sections.map((item) => (
          <button
            key={item}
            onClick={() => setSection(item)}
            className={`rounded-md px-3 py-2 text-xs font-semibold ${
              section === item
                ? "bg-blue-600 text-white"
                : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {section === "Overview" && <OverviewPage />}
      {section === "Regime" && <RegimePage />}
      {section === "Factors" && <FactorPage />}
      {section === "Allocation" && <AllocationPage />}
      {section === "Portfolio Signals" && <SignalsPage />}
      {section === "Backtest" && <BacktestPage />}
      {section === "News" && <NewsPage />}
      {section === "Simulation" && <SimulationPage />}
      {section === "Model Report" && <ModelReportPage />}
    </div>
  );
}
