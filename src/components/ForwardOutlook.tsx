import { Card, StatCard, Table, Badge, ProgressBar } from "@/components/UI";
import { getForwardOutlook, formatPercent, getFactorColor, getRegimeColor } from "@/lib/data";
import { Target, TrendingUp, Activity, Gauge, ShieldAlert, Info } from "lucide-react";
import type { ForecastMonth, OutlookFactor } from "@/types";

const FACTORS: OutlookFactor[] = ["Momentum", "Value", "Quality", "Low Volatility"];

/**
 * T+1 forward view, shown with the model's own accuracy record beside it.
 *
 * The accuracy block is not decoration. A forecast printed without its
 * historical score is an assertion; printed next to the score it made, it is a
 * claim a reader can check. When the sample is too small for a measure to mean
 * anything it is shown as "not enough months" with the count, rather than as a
 * number computed from four observations that would look like evidence.
 */
export function ForwardOutlookPanel() {
  const outlook = getForwardOutlook();

  if (!outlook || !outlook.latest_forecast) {
    return (
      <Card
        title="Forward Outlook — T+1"
        subtitle="Next rebalance month's expected values"
      >
        <div className="py-8 text-center text-sm text-slate-500">
          No forward outlook in this run. The pipeline writes it after the
          allocation optimiser has scored at least one out-of-sample month.
        </div>
      </Card>
    );
  }

  const f: ForecastMonth = outlook.latest_forecast;
  const acc = outlook.accuracy;
  const hitRate = acc?.hit_rate ?? null;
  const ic = acc?.information_coefficient ?? null;

  return (
    <div className="space-y-6">
      <Card
        title="Forward Outlook — T+1"
        subtitle={`Expected values for ${f.month} · ${f.horizon}`}
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Expected Return"
            value={formatPercent(f.expected_portfolio_return)}
            subvalue="decayed trailing mean"
            icon={<TrendingUp className="w-5 h-5" />}
            color={
              f.expected_portfolio_return != null && f.expected_portfolio_return >= 0
                ? "green"
                : "red"
            }
          />
          <StatCard
            label="Expected Volatility"
            value={formatPercent(f.expected_volatility)}
            subvalue="from trailing covariance"
            icon={<Activity className="w-5 h-5" />}
            color="amber"
          />
          <StatCard
            label="Expected Turnover"
            value={formatPercent(f.expected_turnover)}
            subvalue="vs previous weights"
            icon={<Target className="w-5 h-5" />}
            color="slate"
          />
          <StatCard
            label="Regime Call"
            value={
              f.regime_top_probability != null
                ? formatPercent(f.regime_top_probability)
                : "—"
            }
            subvalue={
              f.regime_margin_over_runner_up != null
                ? `${formatPercent(f.regime_margin_over_runner_up)} margin over #2`
                : "regime probability"
            }
            icon={<Gauge className="w-5 h-5" />}
            color={f.regime_top_probability != null && f.regime_top_probability >= 0.7 ? "green" : "amber"}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6 pt-6 border-t border-slate-100">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">
              Factor weights and expected sleeve returns
            </div>
            <div className="space-y-3">
              {FACTORS.map((fac) => {
                const w = f.factor_weights[fac] ?? 0;
                const er = f.expected_factor_returns[fac];
                return (
                  <div key={fac} className="flex items-center gap-3">
                    <div className="flex items-center gap-2 w-32 shrink-0">
                      <div
                        className="w-2.5 h-2.5 rounded-sm"
                        style={{ background: getFactorColor(fac) }}
                      />
                      <span className="text-sm text-slate-700">{fac}</span>
                    </div>
                    <div className="flex-1">
                      <ProgressBar value={w} color={getFactorColor(fac)} />
                    </div>
                    <span className="text-xs font-medium text-slate-700 tabular-nums w-14 text-right">
                      {formatPercent(w)}
                    </span>
                    <span
                      className={`text-xs font-medium tabular-nums w-16 text-right ${
                        er == null
                          ? "text-slate-400"
                          : er >= 0
                            ? "text-emerald-600"
                            : "text-red-600"
                      }`}
                    >
                      {er == null ? "—" : formatPercent(er)}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] text-slate-500">
              Left bar: portfolio weight. Right figure: expected monthly return of
              that factor sleeve.
            </p>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">
              Regime probabilities
            </div>
            <div className="space-y-2">
              {Object.entries(f.regime_probabilities)
                .filter(([, v]) => v != null)
                .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
                .map(([label, p]) => (
                  <div key={label} className="flex items-center gap-3">
                    <span className="text-xs text-slate-600 w-44 shrink-0 truncate">
                      {label}
                    </span>
                    <div className="flex-1">
                      <ProgressBar value={p ?? 0} color={getRegimeColor(label)} />
                    </div>
                    <span className="text-xs tabular-nums text-slate-700 w-12 text-right">
                      {formatPercent(p ?? 0)}
                    </span>
                  </div>
                ))}
            </div>
            {f.sector_tilt_top && Object.keys(f.sector_tilt_top).length > 0 && (
              <>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mt-5 mb-2">
                  Sector tilt implied
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(f.sector_tilt_top).map(([sec, w]) => (
                    <Badge key={sec} color="slate" size="xs">
                      {sec} {formatPercent(w, 1)}
                    </Badge>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="mt-4 flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <Info className="w-4 h-4 text-slate-500 mt-0.5 shrink-0" />
          <p className="text-xs text-slate-600">{f.method}</p>
        </div>
      </Card>

      {acc && (
        <Card
          title="Forecast accuracy — the model's own record"
          subtitle="Every past forecast, scored against what actually happened"
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Directional Hit Rate"
              value={hitRate != null ? formatPercent(hitRate) : "not enough months"}
              subvalue={
                hitRate != null
                  ? `${acc.sleeve_observations} sleeve-months`
                  : `${acc.sleeve_observations} of ${acc.hit_rate_suppressed_below_months} needed`
              }
              icon={<Target className="w-5 h-5" />}
              color={
                hitRate == null
                  ? "slate"
                  : hitRate >= 0.55
                    ? "green"
                    : hitRate >= 0.45
                      ? "amber"
                      : "red"
              }
            />
            <StatCard
              label="Information Coefficient"
              value={ic ? `${ic.value >= 0 ? "+" : ""}${ic.value.toFixed(3)}` : "not enough months"}
              subvalue={ic ? `predicted vs realised, n=${ic.n}` : "sample too small"}
              icon={<Activity className="w-5 h-5" />}
              color={ic == null ? "slate" : ic.value > 0.05 ? "green" : ic.value > 0 ? "amber" : "red"}
            />
            <StatCard
              label="Months Scored"
              value={acc.months_scored}
              subvalue="out-of-sample only"
              icon={<Gauge className="w-5 h-5" />}
              color="blue"
            />
            <StatCard
              label="Mean Abs Error"
              value={
                ic
                  ? formatPercent(
                      FACTORS.reduce((s, k) => s + (acc.mae_by_factor[k]?.mae ?? 0), 0) /
                        FACTORS.length,
                    )
                  : "—"
              }
              subvalue="mean across sleeves"
              icon={<ShieldAlert className="w-5 h-5" />}
              color="slate"
            />
          </div>

          <p className="mt-4 text-xs text-slate-600 leading-relaxed">
            {acc.interpretation}
          </p>

          {acc.calibration.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
                Calibration — was the model's own confidence justified?
              </div>
              <div className="flex flex-wrap gap-4">
                {acc.calibration.map((b) => (
                  <div key={b.bucket} className="text-sm">
                    <span className="text-slate-600">{b.bucket}</span>
                    <span className="ml-2 font-semibold tabular-nums text-slate-900">
                      {b.hit_rate != null ? formatPercent(b.hit_rate) : "n too small"}
                    </span>
                    <span className="ml-1 text-xs text-slate-400">({b.months} mo)</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                A bucket where the hit rate sits well below the confidence the
                model published means it is over-confident. That gap is reported
                rather than hidden.
              </p>
            </div>
          )}

          <div className="mt-4 pt-4 border-t border-slate-100">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
              Most recent forecasts
            </div>
            <Table
              columns={[
                { key: "month", label: "Month" },
                { key: "er", label: "Expected E[r]", align: "right" },
                { key: "vol", label: "Expected vol", align: "right" },
                { key: "regime", label: "Regime call" },
                { key: "conf", label: "Conf", align: "right" },
                { key: "hit", label: "Sleeves right", align: "right" },
                { key: "mae", label: "MAE", align: "right" },
              ]}
              data={[...outlook.forecast_history]
                .slice(-12)
                .reverse()
                .map((row) => {
                  const scored = acc.by_month.find((r) => r.month === row.month);
                  const errs = scored
                    ? FACTORS.map((k) => scored.abs_error[k]).filter(
                        (v): v is number => v != null,
                      )
                    : [];
                  return {
                    month: row.month,
                    er: formatPercent(row.expected_portfolio_return),
                    vol: formatPercent(row.expected_volatility),
                    regime: row.regime_top_label ?? "—",
                    conf:
                      row.regime_top_probability != null
                        ? formatPercent(row.regime_top_probability)
                        : "—",
                    hit: scored && scored.scored_sleeves > 0 ? `${scored.hit}/${scored.scored_sleeves}` : "—",
                    mae: errs.length ? formatPercent(errs.reduce((a, b) => a + b, 0) / errs.length) : "—",
                  };
                })}
              maxHeight="340px"
            />
          </div>

          <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <Info className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
            <p className="text-xs text-amber-800">
              {outlook.how_to_read.suppression_rule}{" "}
              <span className="font-semibold">{outlook.how_to_read.not_advice}</span>
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
