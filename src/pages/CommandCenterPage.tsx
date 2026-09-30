import { AlertTriangle, CheckCircle2, Clock, ShieldAlert, WalletCards } from "lucide-react";
import { Badge, Card, DecisionBadge, ProgressBar, RegimeBadge, StatCard } from "@/components/UI";
import { UniverseCoverage } from "@/components/UniverseCoverage";
import { formatPercent, getOverviewData } from "@/lib/data";
import { formatCurrency, getDecisionSnapshot, loadUserCash, loadUserHoldings, buildTradePlan } from "@/lib/product";

function getDaysSince(dateText: string): number | null {
  if (!dateText || dateText === "—") return null;
  const parsed = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return null;
  const today = new Date();
  const todayDateOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.max(0, Math.floor((todayDateOnly.getTime() - parsed.getTime()) / 86_400_000));
}

function getPortfolioChangeLabel(turnover: number): string {
  if (turnover >= 0.75) return "Very High";
  if (turnover >= 0.4) return "High";
  if (turnover >= 0.15) return "Moderate";
  return "Low";
}

function getPlainMonthlyTitle(decision: string | undefined): string {
  if (decision === "REBALANCE") return "Update the portfolio this month";
  if (decision === "DEFENSIVE") return "Move defensively this month";
  return "Keep current monthly allocation";
}

function getPlainDecisionReason({
  decision,
  regime,
  turnover,
  riskStatus,
}: {
  decision: string | undefined;
  regime?: string;
  turnover: number;
  riskStatus: string;
}): string {
  const changeText =
    turnover >= 0.75
      ? "The raw model saw a major possible reshuffle"
      : turnover >= 0.4
      ? "The raw model saw a meaningful possible reshuffle"
      : "The raw model saw only a limited possible change";

  if (decision === "RETAIN") {
    if (turnover >= 0.4) {
      return `${changeText}, but it did not pass the rebalance gate. Keep the current monthly allocation and use today's guardrail only for practical cleanup trades.`;
    }
    return "The latest monthly decision did not approve a rebalance. Keep the current monthly allocation and execute only practical cleanup trades.";
  }

  if (decision === "DEFENSIVE") {
    return `${changeText} while the market regime is ${regime || "risk-sensitive"}. Reduce unwanted positions first. Add fresh positions slowly instead of buying everything today.`;
  }

  if (riskStatus !== "Normal") {
    return `${changeText}, but today's risk overlay is ${riskStatus}. Follow the monthly direction, then control execution speed based on the daily risk status.`;
  }

  if (decision === "REBALANCE") {
    return `${changeText}, and the rebalance gate approved action. Daily risk is normal, so the monthly rebalance can be executed normally after checking trade sizes.`;
  }

  return "The latest monthly decision did not approve a rebalance. Keep the current monthly allocation and execute only practical cleanup trades.";
}

export function CommandCenterPage({
  onNavigate,
}: {
  onNavigate: (page: "trade-plan" | "performance-trust" | "advanced") => void;
}) {
  const overview = getOverviewData();
  const { decision, allocation, risk, latestMonth, latestEod } = getDecisionSnapshot();
  const holdings = loadUserHoldings();
  const cash = loadUserCash();
  const preview = buildTradePlan(holdings, cash);
  const eodAgeDays = getDaysSince(latestEod);
  const isEodStale = eodAgeDays !== null && eodAgeDays > 3;
  const turnover = allocation?.turnover || 0;
  const portfolioChangeLabel = getPortfolioChangeLabel(turnover);
  const isRetainDecision = (decision?.decision || "RETAIN") === "RETAIN";
  const pausedRows = preview.rows.filter((row) => row.action === "PAUSED");
  const ignoredRows = preview.rows.filter((row) => row.action === "IGNORED");
  const executableRows = preview.rows.filter((row) => row.finalTradeQuantity !== 0);
  const buyRows = executableRows.filter((row) => row.finalTradeQuantity > 0);
  const sellRows = executableRows.filter((row) => row.finalTradeQuantity < 0);
  const plainReason = getPlainDecisionReason({
    decision: decision?.decision,
    regime: overview?.regime_label,
    turnover,
    riskStatus: risk.status,
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Latest Portfolio Command Center</h2>
          <p className="text-sm text-slate-500 mt-1">
            Monthly plan plus daily EOD execution risk for the latest model snapshot.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge color="blue">Model month {latestMonth}</Badge>
          <Badge color={isEodStale || latestEod === "—" ? "amber" : "green"}>Latest EOD {latestEod}</Badge>
          <Badge color="slate">{holdings.length} holding rows saved</Badge>
        </div>
      </div>
      <UniverseCoverage compact />

      {isEodStale && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <div className="flex gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">Data is not fresh enough for a final trading action.</p>
              <p className="mt-1">
                Latest EOD data is {latestEod}, about {eodAgeDays} calendar days old. Use this as a preview until the next
                EOD refresh completes.
              </p>
            </div>
          </div>
        </div>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <DecisionBadge decision={decision?.decision || "RETAIN"} />
              {overview?.regime_label && <RegimeBadge regime={overview.regime_label} />}
              <Badge color={risk.status === "Normal" ? "green" : risk.status === "Caution" ? "amber" : "red"}>
                Daily Risk: {risk.status}
              </Badge>
            </div>
            <h3 className="mt-4 text-2xl font-bold text-slate-950">
              {getPlainMonthlyTitle(decision?.decision)}
            </h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              {plainReason}
            </p>
            {decision?.reason && (
              <p className="mt-2 text-xs text-slate-500">
                Model detail: {decision.reason}
              </p>
            )}
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                onClick={() => onNavigate("trade-plan")}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                View My Trade Plan
              </button>
              <button
                onClick={() => onNavigate("performance-trust")}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Check Trust Score
              </button>
            </div>
          </div>

          <div className="rounded-lg bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Today&apos;s execution guardrail</p>
            <p className="mt-2 text-lg font-bold text-slate-900">{risk.executionMode}</p>
            <p className="mt-2 text-sm leading-5 text-slate-600">{risk.summary}</p>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md bg-white p-2">
                <p className="text-slate-500">Buy/add trades</p>
                <p className="mt-1 font-semibold text-slate-900">{buyRows.length}</p>
              </div>
              <div className="rounded-md bg-white p-2">
                <p className="text-slate-500">Sell/reduce trades</p>
                <p className="mt-1 font-semibold text-slate-900">{sellRows.length}</p>
              </div>
            </div>
            <ul className="mt-4 space-y-2">
              {risk.triggers.map((trigger) => (
                <li key={trigger} className="flex gap-2 text-xs text-slate-600">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                  <span>{trigger}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Model Wants"
          value={
            <span className="text-base">
              Quality {formatPercent(allocation?.quality_weight || 0, 0)} + Low Vol{" "}
              {formatPercent(allocation?.low_volatility_weight || 0, 0)}
            </span>
          }
          subvalue="Main factor preference"
          icon={<CheckCircle2 className="h-5 w-5" />}
          color="green"
        />
        <StatCard
          label={isRetainDecision ? "Raw Model Change" : "Portfolio Change"}
          value={
            <span className="text-base">
              {portfolioChangeLabel} <span className="text-sm font-semibold text-slate-500">({formatPercent(turnover, 0)})</span>
            </span>
          }
          subvalue={isRetainDecision ? "Not executed unless rebalance gate passes" : "How big this month's approved reshuffle is"}
          icon={<Clock className="h-5 w-5" />}
          color={turnover > 0.6 ? "amber" : "blue"}
        />
        <StatCard
          label="Portfolio Value"
          value={formatCurrency(preview.portfolioValue)}
          subvalue="From saved holdings + cash"
          icon={<WalletCards className="h-5 w-5" />}
          color="slate"
        />
        <StatCard
          label="Risk Score"
          value={`${risk.score}`}
          subvalue={risk.status}
          icon={<ShieldAlert className="h-5 w-5" />}
          color={risk.status === "Normal" ? "green" : risk.status === "Caution" ? "amber" : "red"}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Execution Impact" subtitle="What the current risk overlay does to your plan">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Trades executable now</p>
                <p className="mt-1 text-xl font-bold text-slate-900">{executableRows.length}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Paused or too small</p>
                <p className="mt-1 text-xl font-bold text-slate-900">{pausedRows.length + ignoredRows.length}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Stocks after today&apos;s plan</p>
                <p className="mt-1 text-xl font-bold text-slate-900">{preview.stockCountAfter}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Cash after today&apos;s plan</p>
                <p className="mt-1 text-xl font-bold text-slate-900">{formatCurrency(preview.cashAfter)}</p>
              </div>
            </div>
            {(pausedRows.length > 0 || ignoredRows.length > 0 || preview.stockCountAfter <= 2) && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
                <p className="font-semibold text-slate-800">Why this may look smaller than the model portfolio</p>
                <p className="mt-1">
                  This is today&apos;s executable version, not the full target portfolio. Buys can be staggered by the daily
                  risk overlay, and tiny trades can be skipped when they are below the minimum practical trade value.
                </p>
              </div>
            )}
          </div>
        </Card>

        <Card
          title={isRetainDecision ? "Raw Monthly Factor Preference" : "Monthly Factor Preference"}
          subtitle={
            isRetainDecision
              ? "Shown for transparency; current decision is to retain"
              : "Human-readable view of model weights"
          }
        >
          <div className="space-y-3">
            {[
              ["Momentum", allocation?.momentum_weight || 0],
              ["Value", allocation?.value_weight || 0],
              ["Quality", allocation?.quality_weight || 0],
              ["Low Volatility", allocation?.low_volatility_weight || 0],
            ].map(([label, value]) => (
              <div key={label as string}>
                <div className="mb-1 flex justify-between text-xs text-slate-600">
                  <span>{label}</span>
                  <span>{formatPercent(value as number, 0)}</span>
                </div>
                <ProgressBar value={value as number} />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
