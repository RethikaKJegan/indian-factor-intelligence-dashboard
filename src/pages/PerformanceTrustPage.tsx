import { AlertTriangle, ShieldCheck } from "lucide-react";
import { Badge, Card, Table } from "@/components/UI";
import { UniverseCoverage } from "@/components/UniverseCoverage";
import { formatNumber, formatPercent } from "@/lib/data";
import { getBenchmarkVerdicts, getDecisionSnapshot, getModelComparisonRows } from "@/lib/product";

export function PerformanceTrustPage() {
  const verdicts = getBenchmarkVerdicts();
  const summaries = [verdicts.dynamic, verdicts.staticMix, verdicts.nifty].filter(Boolean);
  const comparisonRows = getModelComparisonRows();
  const { decision, risk, latestMonth, latestEod } = getDecisionSnapshot();
  const actionable = decision?.decision === "REBALANCE" || decision?.decision === "DEFENSIVE";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Performance & Trust</h2>
        <p className="mt-1 text-sm text-slate-500">
          Plain-English checks for whether the model deserves trust.
        </p>
      </div>

      <Card title="Current Deployability" subtitle="Whether the latest model output should produce trades now">
        <div className={`rounded-lg p-4 text-sm leading-6 ${actionable ? "bg-amber-50 text-amber-900" : "bg-slate-50 text-slate-700"}`}>
          <div className="flex flex-wrap gap-2">
            <Badge color={actionable ? "amber" : "slate"}>{decision?.decision || "RETAIN"}</Badge>
            <Badge color={risk.status === "Normal" ? "green" : "amber"}>{risk.executionMode}</Badge>
            <Badge color="blue">Model month {latestMonth}</Badge>
            <Badge color="green">EOD {latestEod}</Badge>
          </div>
          <p className="mt-3 font-semibold">
            {actionable
              ? "Current output is trade-actionable, subject to the daily execution guardrail."
              : "Current output is not an automatic rebalance instruction."}
          </p>
          <p className="mt-1">
            {actionable
              ? "Trade Plan can convert approved model targets into exact quantities, then reduce or pause buys based on daily risk."
              : "Raw targets, factor tilts, and sector exposures are shown for transparency, but Trade Plan should not force buys or sells until the rebalance gate passes."}
          </p>
        </div>
      </Card>

      <Card title="Trust Scorecard" subtitle="No hidden benchmark failures">
        <Table
          maxHeight="360px"
          columns={[
            { key: "question", label: "Question" },
            { key: "answer", label: "Answer" },
          ]}
          data={verdicts.rows}
        />
      </Card>

      <Card title="Benchmark Summary" subtitle="Current available strategies in the shipped data">
        <Table
          maxHeight="420px"
          columns={[
            { key: "strategy", label: "Strategy" },
            { key: "cagr", label: "Avg yearly growth", align: "right" },
            { key: "sharpe", label: "Sharpe", align: "right" },
            { key: "drawdown", label: "Worst fall", align: "right" },
            { key: "turnover", label: "Avg turnover", align: "right" },
          ]}
          data={summaries.map((summary) => ({
            strategy: summary!.strategy_name,
            cagr: formatPercent(summary!.cagr, 2),
            sharpe: formatNumber(summary!.sharpe, 2),
            drawdown: formatPercent(summary!.max_drawdown, 2),
            turnover: formatPercent(summary!.avg_turnover, 2),
          }))}
        />
      </Card>

      <UniverseCoverage />

      <Card
        title="Model / Strategy Selection Score"
        subtitle="Current scaffold: higher score balances return, drawdown, Sharpe, Calmar, and turnover"
      >
        <Table
          maxHeight="360px"
          columns={[
            { key: "strategy", label: "Strategy" },
            { key: "score", label: "Score", align: "right" },
            { key: "cagr", label: "Growth", align: "right" },
            { key: "drawdown", label: "Worst fall", align: "right" },
            { key: "turnover", label: "Turnover", align: "right" },
          ]}
          data={comparisonRows.map((row) => ({
            strategy: row.strategy,
            score: formatNumber(row.score, 2),
            cagr: formatPercent(row.cagr, 2),
            drawdown: formatPercent(row.maxDrawdown, 2),
            turnover: formatPercent(row.turnover, 2),
          }))}
        />
        <p className="mt-4 text-xs leading-5 text-slate-500">
          When the Python pipeline adds GMM/HMM/Markov/rule-based candidates, this table should rank those candidates
          using walk-forward after-cost metrics rather than model name.
        </p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Required Caveats" subtitle="These must remain visible in the user product">
          <div className="space-y-3">
            {[
              "The production model currently uses 189 usable stocks, not all 200 Nifty 200 symbols.",
              "The 11 excluded symbols need reliable historical price and fundamental data before model inclusion.",
              "Backtests may contain survivorship bias unless historical Nifty 200 constituents are reconstructed.",
              "Monthly targets come from the model; daily execution modes come from predefined risk rules.",
              "The LLM explains model outputs. It does not decide trades.",
              "This is not suitable for blind auto-trading.",
            ].map((item) => (
              <div key={item} className="flex gap-2 text-sm leading-6 text-slate-700">
                <AlertTriangle className="mt-1 h-4 w-4 shrink-0 text-amber-500" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="User-Friendly Translations" subtitle="Terms normal users should see">
          <div className="grid grid-cols-2 gap-2 text-sm">
            {[
              ["CAGR", "Average yearly growth"],
              ["Drawdown", "Fall from previous high"],
              ["Volatility", "Expected ups and downs"],
              ["Target weight", "Model wants you to hold"],
              ["Regime", "Market condition"],
              ["Turnover", "How much changes"],
            ].map(([technical, simple]) => (
              <div key={technical} className="rounded-lg bg-slate-50 p-3">
                <p className="font-semibold text-slate-900">{technical}</p>
                <p className="text-xs text-slate-500">{simple}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Current Product Claim">
        <div className="rounded-lg bg-emerald-50 p-4 text-sm leading-6 text-emerald-900">
          <div className="mb-2 flex items-center gap-2 font-semibold">
            <ShieldCheck className="h-4 w-4" />
            Allowed claim
          </div>
          <p>
            The system uses a monthly factor-based portfolio model for the clean Nifty 200 modelling universe and a
            daily EOD risk overlay for execution control. Benchmark results, costs, and caveats must be shown alongside
            performance.
          </p>
          <div className="mt-3">
            <Badge color="green">Decision support only</Badge>
          </div>
        </div>
      </Card>
    </div>
  );
}
