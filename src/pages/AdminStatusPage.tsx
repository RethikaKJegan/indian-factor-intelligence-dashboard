import { Badge, Card, Table } from "@/components/UI";
import { getEodRefreshStatus, getLangGraphRunReport } from "@/lib/data";
import { assessDailyRisk } from "@/lib/product";

export function AdminStatusPage() {
  const eod = getEodRefreshStatus();
  const eodMeta = eod as any;
  const report = getLangGraphRunReport();
  const risk = assessDailyRisk();

  const rows = [
    { item: "EOD refresh status", value: eod.status || "not loaded" },
    { item: "Requested date", value: eod.requested_date || "—" },
    { item: "Resolved EOD date", value: eod.resolved_date || "—" },
    { item: "Stock rows", value: String(eod.stock_rows || 0) },
    { item: "Index rows", value: String(eod.index_rows || 0) },
    { item: "Started at", value: eod.started_at || "—" },
    { item: "Finished at", value: eod.finished_at || "—" },
    { item: "Last attempted date", value: eodMeta.last_attempted_date || "—" },
    { item: "Last attempted status", value: eodMeta.last_attempted_status || "—" },
    { item: "Daily risk status", value: `${risk.status} (${risk.executionMode})` },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Admin Status</h2>
        <p className="mt-1 text-sm text-slate-500">
          Pipeline status for local data snapshots. Vercel cron wiring comes at deployment time.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Badge color={eod.status === "ok" ? "green" : "amber"}>EOD {eod.status}</Badge>
        <Badge color={report.human_approval_required ? "amber" : "green"}>
          Human approval {report.human_approval_required ? "required" : "not required"}
        </Badge>
        <Badge color={risk.status === "Normal" ? "green" : "amber"}>Risk {risk.status}</Badge>
      </div>

      <Card title="Pipeline Snapshot" subtitle={eod.message}>
        <Table
          maxHeight="420px"
          columns={[
            { key: "item", label: "Item" },
            { key: "value", label: "Value" },
          ]}
          data={rows}
        />
      </Card>

      {eodMeta.last_attempted_status && (
        <Card title="Latest Attempt Note" subtitle="A failed/no-data attempt does not overwrite the last successful EOD">
          <div className="rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700">
            <p>
              Last successful resolved EOD remains <span className="font-semibold">{eod.resolved_date || "—"}</span>.
              Latest attempted refresh for <span className="font-semibold">{eodMeta.last_attempted_date}</span> returned{" "}
              <span className="font-semibold">{eodMeta.last_attempted_status}</span>.
            </p>
            {eodMeta.last_attempted_message && (
              <p className="mt-2 text-xs text-slate-500">{eodMeta.last_attempted_message}</p>
            )}
          </div>
        </Card>
      )}

      <Card title="Graph / Model Warnings">
        {report.warnings.length ? (
          <ul className="space-y-2 text-sm text-slate-700">
            {report.warnings.map((warning) => (
              <li key={warning} className="rounded-lg bg-amber-50 p-3 text-amber-800">
                {warning}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No model warnings in the current snapshot.</p>
        )}
      </Card>

      <Card title="Deployment Note">
        <p className="text-sm leading-6 text-slate-600">
          Local development tests refresh manually with{" "}
          <code className="rounded bg-slate-100 px-1">scripts\run_daily_eod_pipeline.ps1</code>. After deployment, cron
          should trigger the same EOD/model pipeline through GitHub Actions or a worker. Vercel should serve the generated
          JSON; heavy Python model jobs should not run inside a short serverless request.
        </p>
      </Card>
    </div>
  );
}
