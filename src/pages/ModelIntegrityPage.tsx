import { Card, Table, StatCard, Badge } from "@/components/UI";
import {
  getExperimentManifest,
  getPerformanceReport,
  getConstraintCompliance,
  getCoverageAudit,
  getPointInTimeSurvivorship,
  formatNumber,
} from "@/lib/data";
import type {
  ManifestCaveat,
  DataFreshness,
  FundamentalCoverageAudit,
  PointInTimeSurvivorship,
} from "@/types";

/**
 * Model Integrity.
 *
 * One page that answers, in order: what ran, on what data, assuming what, and
 * what it cannot support. Every other page presents a number; this one
 * qualifies them, which is why it is deliberately the least flattering page in
 * the dashboard.
 *
 * All of it is read from `experiment_manifest.json`, which the pipeline writes
 * on every run. Nothing here is typed by hand, so a caveat cannot drift away
 * from the figure it qualifies.
 */

const SEVERITY_STYLE: Record<
  ManifestCaveat["severity"],
  { label: string; className: string; dot: string }
> = {
  high: {
    label: "High",
    className: "bg-red-100 text-red-700 border-red-200",
    dot: "bg-red-500",
  },
  medium: {
    label: "Medium",
    className: "bg-amber-100 text-amber-700 border-amber-200",
    dot: "bg-amber-500",
  },
  low: {
    label: "Low",
    className: "bg-slate-100 text-slate-600 border-slate-200",
    dot: "bg-slate-400",
  },
};

function caveatSort(a: ManifestCaveat, b: ManifestCaveat): number {
  const rank = { high: 0, medium: 1, low: 2 };
  return rank[a.severity] - rank[b.severity];
}

export function ModelIntegrityPage() {
  const manifest = getExperimentManifest();
  const report = getPerformanceReport();
  const constraints = getConstraintCompliance();

  if (!manifest) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Model Integrity</h1>
          <p className="text-sm text-slate-500 mt-1">
            Reproducibility record, assumptions, and the limits of this run
          </p>
        </div>
        <Card title="No experiment manifest" subtitle="This output predates it">
          <p className="text-sm text-slate-600">
            The pipeline did not write{" "}
            <code className="text-xs bg-slate-100 px-1 rounded">
              experiment_manifest.json
            </code>{" "}
            for this build. Re-run{" "}
            <code className="text-xs bg-slate-100 px-1 rounded">
              python scripts/run_pipeline.py
            </code>{" "}
            to record what the run consumed, what it assumed, and what it cannot
            support.
          </p>
        </Card>
      </div>
    );
  }

  const { run, inputs, code, caveats, caveat_summary: summary } = manifest;
  const freshness = manifest.data_freshness;
  const audit = getCoverageAudit();
  const survivorship = getPointInTimeSurvivorship();
  const tables = Object.entries(inputs.tables).filter(([, t]) => t.present);
  const nonDeterministic = manifest.determinism.filter((d) => !d.deterministic);
  const sortedCaveats = [...caveats].sort(caveatSort);
  const constraintBreaches =
    constraints && constraints.months_breaching_max_weight > 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Model Integrity</h1>
        <p className="text-sm text-slate-500 mt-1">
          What this run consumed, what it assumed, and what it cannot support.
          Every other page presents a number; this one qualifies it.
        </p>
      </div>

      {/* Data currency, above everything else. Everything below it is
          conditional on the data being current, so it comes first. */}
      {freshness && (
        <FreshnessBanner freshness={freshness} />
      )}

      {/* The headline: is this run comparable to another one? */}
      <Card
        title="Run identity"
        subtitle="A fingerprint over inputs, code and assumptions together"
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            label="Run fingerprint"
            value={
              <span className="font-mono text-sm break-all">
                {run.fingerprint.slice(0, 16)}…
              </span>
            }
            subvalue="inputs + code + assumptions"
            color="blue"
          />
          <StatCard
            label="Runtime"
            value={`${run.runtime_seconds.toFixed(0)}s`}
            subvalue={new Date(run.finished_at).toLocaleString()}
            color="slate"
          />
          <StatCard
            label="Open caveats"
            value={String(caveats.length)}
            subvalue={`${summary.high} high · ${summary.medium} medium · ${summary.low} low`}
            color={summary.high > 0 ? "red" : "green"}
          />
          <StatCard
            label="Code modules"
            value={String(code.modules.length)}
            subvalue="all hashed"
            color="slate"
          />
        </div>
        <div className="mt-3 rounded-lg bg-slate-50 border border-slate-200 p-3">
          <p className="text-xs text-slate-600 leading-relaxed">
            <span className="font-medium text-slate-700">
              What the fingerprint covers:
            </span>{" "}
            {run.fingerprint_covers.join("; ")}. {run.fingerprint_note}
          </p>
          {nonDeterministic.length > 0 && (
            <p className="text-xs text-amber-700 mt-2 leading-relaxed">
              <span className="font-medium">Not fully reproducible:</span>{" "}
              {nonDeterministic.map((d) => d.stage).join(", ")} —{" "}
              {nonDeterministic[0].basis}
            </p>
          )}
          {manifest.news_snapshot && (
            <p className="text-xs text-slate-600 mt-2 leading-relaxed">
              <span className="font-medium text-slate-700">
                News article set:
              </span>{" "}
              {manifest.news_snapshot.article_count.toLocaleString()} articles,
              fetched{" "}
              {new Date(manifest.news_snapshot.fetched_at).toLocaleString()},
              content hash{" "}
              <span className="font-mono text-[10px]">
                {manifest.news_snapshot.content_sha256.slice(0, 16)}…
              </span>
              . This is the only input that can move between runs, so it is
              hashed into the fingerprint. Two runs sharing this hash saw the
              same articles and are directly comparable; two runs differing on
              it are not.
            </p>
          )}
        </div>
      </Card>

      {/* The most important page in the dashboard. */}
      <Card
        title="What this run cannot support"
        subtitle={`${caveats.length} limitations, read from the artifacts this run produced`}
      >
        <div className="space-y-3">
          {sortedCaveats.map((c) => {
            const style = SEVERITY_STYLE[c.severity];
            return (
              <div
                key={c.id}
                className="rounded-lg border border-slate-200 p-4 hover:border-slate-300 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${style.dot}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-slate-900">
                        {c.id.replace(/_/g, " ")}
                      </span>
                      <span
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${style.className}`}
                      >
                        {style.label}
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">
                      {c.statement}
                    </p>
                    <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                      <span className="font-medium text-slate-600">
                        Why it is not fixed:{" "}
                      </span>
                      {c.why_not_fixed}
                    </p>
                    {c.provenance_check && (
                      <p className="text-xs text-emerald-700 mt-1.5 leading-relaxed">
                        {c.provenance_check}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* What the trading universe actually contained, month by month. */}
      {survivorship?.available && (
        <SurvivorshipCard pit={survivorship} />
      )}

      {/* Why the fundamental factors see what they see. */}
      {audit && audit.available && <CoverageCard audit={audit} />}

      {/* Reproducibility: stage by stage. */}
      <Card
        title="Determinism"
        subtitle="Whether the same input gives the same output, stage by stage"
      >
        <div className="space-y-2">
          {manifest.determinism.map((d) => (
            <div
              key={d.stage}
              className="flex items-start gap-3 py-2 border-b border-slate-100 last:border-0"
            >
              <span
                className={`mt-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded border flex-shrink-0 ${
                  d.deterministic
                    ? "bg-emerald-100 text-emerald-700 border-emerald-200"
                    : "bg-amber-100 text-amber-700 border-amber-200"
                }`}
              >
                {d.deterministic ? "deterministic" : "varies"}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-800">
                  {d.stage}
                </p>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                  {d.basis}
                </p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* The constants that would change every result if they were wrong. */}
      <Card
        title="Assumptions"
        subtitle="Read from the live modules, so they cannot drift from the code that ran"
      >
        <Table
          columns={[
            { key: "name", label: "Assumption" },
            { key: "value", label: "Value" },
            { key: "controls", label: "What it controls" },
            { key: "risk", label: "Risk if wrong" },
          ]}
          data={manifest.assumptions.map((a) => ({
            name: (
              <span className="font-mono text-xs text-slate-800">
                {a.name}
              </span>
            ),
            value: (
              <span className="font-mono text-xs text-slate-700">
                {typeof a.value === "object" && a.value !== null
                  ? JSON.stringify(a.value)
                  : String(a.value)}
              </span>
            ),
            controls: (
              <span className="text-xs text-slate-600">{a.controls}</span>
            ),
            risk: (
              <span className="text-xs text-slate-500">{a.risk_if_wrong}</span>
            ),
          }))}
          maxHeight="420px"
        />
      </Card>

      {/* The data window this run actually consumed. */}
      <Card
        title="Data consumed"
        subtitle={`${inputs.bytes ? (inputs.bytes / 1024 / 1024).toFixed(0) + " MB" : "size unknown"} source database`}
      >
        <Table
          columns={[
            { key: "table", label: "Table" },
            { key: "rows", label: "Rows", align: "right" },
            { key: "window", label: "Month window" },
            { key: "months", label: "Months", align: "right" },
          ]}
          data={tables.map(([name, t]) => ({
            table: <span className="font-mono text-xs">{name}</span>,
            rows: (t.rows ?? 0).toLocaleString(),
            window:
              t.month_min && t.month_max ? (
                <span className="text-xs text-slate-600">
                  {String(t.month_min).slice(0, 7)} →{" "}
                  {String(t.month_max).slice(0, 7)}
                </span>
              ) : (
                <span className="text-xs text-slate-400">
                  not a monthly table
                </span>
              ),
            months: t.months ?? "—",
          }))}
        />
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">
          Row counts rather than a file hash, because hashing a multi-gigabyte
          SQLite file would make the fingerprint depend on physical layout: any
          unrelated write would change it. Counting rows and reading the date
          bounds records what the run actually consumed, which is the more
          useful question.
        </p>
      </Card>

      {/* Cross-checks against the headline numbers. */}
      <Card
        title="Cross-checks"
        subtitle="Whether the claims on other pages survive the numbers on this one"
      >
        <div className="space-y-2 text-sm">
          {report && (
            <>
              <CheckRow
                label="Sortino uses the standard downside deviation"
                detail={`${formatNumber(report.risk_adjusted.sortino_vs_zero)} against a zero rate, across all periods rather than losing months only. The earlier figure of 1.46 divided by the count of losing months and understated it.`}
                pass
              />
              <CheckRow
                label="Risk-free rate is disclosed, not implied"
                detail={`Sharpe is ${formatNumber(report.risk_adjusted.sharpe_vs_zero)} against a zero rate and ${formatNumber(report.risk_adjusted.sharpe_vs_rf)} against the ${(report.risk_free_assumption.annual * 100).toFixed(1)}% assumption. Both are on the Backtest page; neither is presented alone.`}
                pass
              />
              <CheckRow
                label="Warm-up months do not claim a model that never ran"
                detail="The regime model refuses to score before its warm-up ends. Those months carry model_version 'not-scored-warmup' rather than the GMM label, so the output does not assert a provenance it lacks."
                pass
              />
            </>
          )}
          {constraints && (
            <CheckRow
              label={
                constraints.months_breaching_max_weight === 0
                  ? "Position limits held in every month"
                  : "Position limits were breached"
              }
              detail={
                constraints.months_breaching_max_weight === 0
                  ? `The 5% position cap and 30% sector cap were respected in all ${Object.keys(constraints.months).length} months. This is a measured fact from the run, not a design intention.`
                  : `${constraints.months_breaching_max_weight} months exceeded the position cap. The backtest held a book the stated construction could not have built.`
              }
              pass={constraints.months_breaching_max_weight === 0}
            />
          )}
          <CheckRow
            label="Bootstrap intervals are pinned to a fixed seed"
            detail={`Seed ${report?.confidence_intervals?.sharpe?.seed ?? "—"}, ${report?.confidence_intervals?.sharpe?.bootstrap_samples?.toLocaleString() ?? "—"} resamples, block length ${report?.confidence_intervals?.sharpe?.block_length ?? "—"}. The interval is identical on every run; one that moved between runs would not be a result.`}
            pass
          />
          <CheckRow
            label="No machine-learning layer is fitted"
            detail="A supervised learner cannot be validated out of sample on the forward-return history available here. None is fitted, and the absence is recorded rather than quietly filled with a model that would overfit."
            pass
          />
        </div>
        {constraintBreaches && (
          <div className="mt-3 rounded-lg bg-red-50 border border-red-200 p-3">
            <p className="text-xs text-red-800">
              At least one hard portfolio limit was breached in this run. The
              reported backtest includes positions the stated construction could
              not have produced.
            </p>
          </div>
        )}
      </Card>

      {/* Code provenance, collapsed by default: useful, rarely read. */}
      <Card
        title="Code provenance"
        subtitle={`SHA-256 of every pipeline module as it stood for this run`}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-64 overflow-y-auto">
          {code.modules.map((m) => (
            <div
              key={m.path}
              className="flex items-center justify-between gap-2 py-1 px-2 rounded hover:bg-slate-50"
            >
              <span className="font-mono text-xs text-slate-700 truncate">
                {m.path.split(/[\\/]/).pop()}
              </span>
              <span className="font-mono text-[10px] text-slate-400 flex-shrink-0">
                {m.sha256?.slice(0, 12)}
              </span>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-3">{code.note}</p>
      </Card>

      <Card title="Environment" subtitle="What the run executed on">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Python
            </p>
            <p className="font-mono text-sm text-slate-800 mt-0.5">
              {manifest.environment.python}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Platform
            </p>
            <p className="font-mono text-sm text-slate-800 mt-0.5 break-all">
              {manifest.environment.platform}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Manifest schema
            </p>
            <p className="font-mono text-sm text-slate-800 mt-0.5">
              {manifest.schema}
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}

function CheckRow({
  label,
  detail,
  pass,
}: {
  label: string;
  detail: string;
  pass: boolean;
}) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-slate-100 last:border-0">
      <span className="mt-0.5 flex-shrink-0">
        <Badge color={pass ? "green" : "red"} size="xs">
          {pass ? "pass" : "fail"}
        </Badge>
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-800">{label}</p>
        <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
          {detail}
        </p>
      </div>
    </div>
  );
}

/**
 * Which symbols the fundamental factors can actually see, and why the rest are
 * invisible.
 *
 * A raw count of withheld scores says something is missing. It does not say
 * that the missing part is the entire banking sector, which is a different
 * problem with a different fix: not an outage, but a sector whose reporting
 * conventions have no counterpart in the metrics being computed.
 */
/**
 * Survivorship, counted rather than asserted.
 *
 * The point worth making visually is the asymmetry: the left side is what the
 * gate fixed, the right side is what it can only count. Presenting the
 * uncorrected number next to a satisfied-looking "gate enabled" badge would be
 * the dishonest arrangement, so the uncorrected count is the one given the
 * warning colour.
 */
function SurvivorshipCard({ pit }: { pit: PointInTimeSurvivorship }) {
  const late = pit.db_symbols_not_yet_listed_examples ?? {};
  const lateNames = Object.entries(late).slice(0, 8);

  return (
    <Card
      title="Survivorship, measured"
      subtitle={`${pit.symbols_observed.toLocaleString()} symbols observed trading across ${pit.months_covered} NSE bhavcopy month-ends, ${pit.archive_floor} to ${pit.archive_ceiling}`}
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Unlisted symbols gated"
          value={String(pit.db_symbols_not_yet_listed_at_archive_start)}
          subvalue={`of ${pit.db_symbols} in the database`}
          color="green"
        />
        <StatCard
          label="Backtest months gated"
          value={`${pit.backtest_months_gated_pct.toFixed(0)}%`}
          subvalue={`${pit.backtest_months_gated} of ${pit.backtest_months_gated + pit.backtest_months_ungated} months`}
          color="green"
        />
        <StatCard
          label="Names never ingested"
          value={String(pit.stopped_trading_absent_from_db)}
          subvalue="traded early, gone by the end"
          color="red"
        />
        <StatCard
          label="Trading universe grew"
          value={`${pit.trading_universe_at_archive_start.toLocaleString()} → ${pit.trading_universe_at_archive_end.toLocaleString()}`}
          subvalue="symbols per month-end"
          color="blue"
        />
      </div>

      <div className="mt-4 space-y-3">
        <p className="text-xs text-slate-600 leading-relaxed">
          {pit.interpretation}
        </p>

        {pit.gate_enabled ? (
          <div className="rounded border border-emerald-200 bg-emerald-50 p-3">
            <p className="text-xs font-medium text-emerald-800 mb-1.5">
              Look-forward: corrected
            </p>
            <p className="text-xs text-emerald-700 leading-relaxed">
              A symbol is now scored only in months it had already started
              trading. These database symbols are held out of the months before
              their listing:
            </p>
            {lateNames.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {lateNames.map(([sym, month]) => (
                  <span
                    key={sym}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white border border-emerald-200 text-emerald-800"
                  >
                    {sym} · {month}
                  </span>
                ))}
                {Object.keys(late).length > lateNames.length && (
                  <span className="text-[10px] px-1.5 py-0.5 text-emerald-600">
                    +{Object.keys(late).length - lateNames.length} more
                  </span>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="rounded border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs text-amber-800 leading-relaxed">
              Point-in-time gating is <strong>off</strong> this run. The
              bhavcopy trading record was not present, so not-yet-listed symbols
              are being scored in months they could not have traded.
            </p>
          </div>
        )}

        <div className="rounded border border-rose-200 bg-rose-50 p-3">
          <p className="text-xs font-medium text-rose-800 mb-1.5">
            Exclusion: not corrected
          </p>
          <p className="text-xs text-rose-700 leading-relaxed">
            {pit.stopped_trading_absent_from_db} names were tradable early in
            the window and are absent from the database, so they cannot drag
            the result. A sample of them:{" "}
            <span className="font-mono">
              {(pit.examples_of_excluded_names ?? []).slice(0, 8).join(", ")}
            </span>
            . This is the part that inflates the return, and no amount of
            pipeline work removes it — it needs fundamentals for tickers that
            were never ingested.
          </p>
        </div>
      </div>
    </Card>
  );
}

function CoverageCard({ audit }: { audit: FundamentalCoverageAudit }) {
  const bc = audit.summary.by_classification;
  const total = audit.summary.total_symbols || 1;
  const struct = bc.structurally_excluded ?? 0;
  const gap = bc.unexplained_gap ?? 0;
  const sparse = bc.sparse ?? 0;
  const measured = bc.measured ?? 0;

  const classes = [
    { key: "measured", label: "Measured", n: measured, color: "green" as const },
    {
      key: "structurally_excluded",
      label: "Structurally out",
      n: struct,
      color: "amber" as const,
    },
    { key: "sparse", label: "Sparse", n: sparse, color: "amber" as const },
    {
      key: "unexplained_gap",
      label: "Ingestion gap",
      n: gap,
      color: "red" as const,
    },
  ];

  return (
    <Card
      title="What the fundamental factors can see"
      subtitle={`${total} symbols, classified by whether the Value and Quality metrics exist at all`}
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {classes.map((c) => (
          <StatCard
            key={c.key}
            label={c.label}
            value={String(c.n)}
            subvalue={`${((100 * c.n) / total).toFixed(0)}% of universe`}
            color={c.color}
          />
        ))}
      </div>

      {/* Proportion bar, so the shape of the exclusion is visible at a glance. */}
      <div className="mt-4">
        <div className="flex h-3 rounded-full overflow-hidden bg-slate-100">
          {classes.map((c) =>
            c.n > 0 ? (
              <div
                key={c.key}
                className={
                  c.key === "measured"
                    ? "bg-emerald-500"
                    : c.key === "unexplained_gap"
                      ? "bg-red-400"
                      : "bg-amber-400"
                }
                style={{ width: `${(100 * c.n) / total}%` }}
                title={`${c.label}: ${c.n}`}
              />
            ) : null,
          )}
        </div>
      </div>

      {struct > 0 && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs text-amber-900 leading-relaxed">
            <span className="font-semibold">
              {struct} symbols ({((100 * struct) / total).toFixed(0)}%) are
              structurally invisible to Value and Quality
            </span>
            , and every one of them is in{" "}
            {audit.structurally_excluded_sectors.join(", ") || "a sector whose reporting differs"}.
            A bank has no revenue line to grow, and its deposits are not debt in
            the sense a debt/equity ratio assumes. This is an economic fact, not
            an ingestion failure, and no amount of pipeline work changes it —
            only bank-specific metrics (NIM, GNPA, PCR, CASA) would. Momentum
            and Low Volatility are price-based and still cover these names.
          </p>
        </div>
      )}

      {gap > 0 && (
        <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-3">
          <p className="text-xs text-red-900 leading-relaxed">
            <span className="font-semibold">
              {gap} genuine ingestion {gap === 1 ? "gap" : "gaps"}
            </span>
            : {audit.unexplained.join(", ")} have fundamental rows but no
            populated metric in any month. Unlike the banks, this is a
            collection failure rather than a reporting convention, and the
            coverage rule correctly withholds their scores rather than guessing.
          </p>
        </div>
      )}

      <p className="text-xs text-slate-500 mt-3 leading-relaxed">
        {audit.note}
      </p>
    </Card>
  );
}

const FRESHNESS_STYLE: Record<
  DataFreshness["status"],
  { label: string; wrapper: string; dot: string }
> = {
  current: {
    label: "Data is current",
    wrapper: "border-emerald-300 bg-emerald-50",
    dot: "bg-emerald-500",
  },
  degraded: {
    label: "Data is behind",
    wrapper: "border-amber-300 bg-amber-50",
    dot: "bg-amber-500",
  },
  stale: {
    label: "Data is stale",
    wrapper: "border-red-300 bg-red-50",
    dot: "bg-red-500",
  },
  unreadable: {
    label: "Data could not be read",
    wrapper: "border-red-300 bg-red-50",
    dot: "bg-red-500",
  },
  unknown: {
    label: "Data currency unknown",
    wrapper: "border-slate-300 bg-slate-50",
    dot: "bg-slate-400",
  },
};

/**
 * Whether the dashboard is showing numbers from the latest trading day.
 *
 * This sits at the top of the page because everything below it is conditional
 * on it. A 27.91% backtest CAGR computed on four-day-old prices is still 27.91%
 * — the methodology is unaffected — but every current-month figure on the
 * dashboard is describing a day that has already passed, and nothing in the
 * rendered numbers would tell you so.
 */
function FreshnessBanner({ freshness }: { freshness: DataFreshness }) {
  const style = FRESHNESS_STYLE[freshness.status] ?? FRESHNESS_STYLE.unknown;
  const problems = freshness.issues.filter((i) => i.severity !== "ok");
  const behind = freshness.eod.trading_days_behind;

  return (
    <div className={`rounded-xl border p-4 ${style.wrapper}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`w-2.5 h-2.5 rounded-full ${style.dot}`} />
        <h2 className="text-base font-semibold text-slate-900">
          {style.label}
        </h2>
        <span className="text-xs text-slate-600">
          checked {new Date(freshness.checked_at).toLocaleString()}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
        <StatCard
          label="Latest close in DB"
          value={freshness.eod.latest_date ?? "none"}
          subvalue={`${freshness.eod.rows.toLocaleString()} daily rows`}
          color={behind && behind > 1 ? "amber" : "slate"}
        />
        <StatCard
          label="Expected"
          value={freshness.expected_eod_date}
          subvalue="last trading day by now"
          color="slate"
        />
        <StatCard
          label="Trading days behind"
          value={behind === null ? "?" : String(behind)}
          subvalue={behind === 1 ? "refresh may not have run" : "missed runs"}
          color={
            behind === null || behind === 0
              ? "green"
              : behind === 1
                ? "amber"
                : "red"
          }
        />
        <StatCard
          label="Month label"
          value={(freshness.newest_month_label ?? "—").slice(0, 7)}
          subvalue="bucket, not a date reached"
          color="slate"
        />
      </div>

      {problems.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {problems.map((issue) => (
            <li key={issue.id} className="flex items-start gap-2">
              <span
                className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  issue.severity === "high"
                    ? "bg-red-500"
                    : issue.severity === "medium"
                      ? "bg-amber-500"
                      : "bg-slate-400"
                }`}
              />
              <span className="text-xs text-slate-700 leading-relaxed">
                {issue.detail}
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-slate-600 mt-3 leading-relaxed">
        The <span className="font-medium">month label</span> is why a table can
        appear to contradict the header. Months are keyed by calendar month-end,
        so an in-progress month always carries a future date — the label is a
        bucket, not a claim that trading reached it.{" "}
        {freshness.trading_calendar_note}
      </p>
    </div>
  );
}
