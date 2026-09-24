import { Card, StatCard, Badge, Table } from "@/components/UI";
import { BarChart } from "@/components/Charts";
import { getNewsArticles, getNewsDailyFeatures, getNewsFeatures, formatPercent } from "@/lib/data";
import { Newspaper, ExternalLink, AlertTriangle, Activity, CalendarDays } from "lucide-react";

function hostLabel(source: string) {
  return source.replace(/^www\./, "");
}

function timeAgo(value: string) {
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return "";
  const mins = Math.max(0, Math.round((Date.now() - ts) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function NewsPage() {
  const articles = getNewsArticles();
  const latest = articles.slice(0, 12);
  const daily = getNewsDailyFeatures();
  const monthly = getNewsFeatures();
  const latestDay = daily.length ? daily[daily.length - 1] : null;
  const latestMonth = monthly.length ? monthly[monthly.length - 1] : null;
  const riskRows = latest
    .filter((a) => a.risk_event_count > 0 || a.is_negative)
    .slice(0, 8)
    .map((a) => ({
      time: new Date(a.published_at).toLocaleString(),
      source: hostLabel(a.source),
      title: (
        <a className="font-medium text-blue-700 hover:text-blue-900" href={a.url} target="_blank" rel="noreferrer">
          {a.title}
        </a>
      ),
      risk: a.risk_event_count,
      sentiment: a.sentiment.toFixed(2),
    }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Financial News Intelligence</h2>
        <p className="text-sm text-slate-500 mt-1">
          Real RSS articles, clickable sources, daily risk evidence, and monthly news features for the regime layer
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="RSS Articles" value={articles.length} subvalue="Latest fetched run" icon={<Newspaper className="w-5 h-5" />} color="blue" />
        <StatCard label="Latest Day Articles" value={latestDay?.article_count ?? 0} subvalue={latestDay?.date ?? "No day"} icon={<CalendarDays className="w-5 h-5" />} color="green" />
        <StatCard label="Negative Ratio" value={formatPercent(latestDay?.negative_ratio ?? 0)} subvalue="Daily news stress" icon={<AlertTriangle className="w-5 h-5" />} color={(latestDay?.negative_ratio ?? 0) > 0.35 ? "red" : "amber"} />
        <StatCard label="News Confidence" value={formatPercent(latestMonth?.news_confidence ?? latestDay?.news_confidence ?? 0)} subvalue={latestMonth?.month ?? "Monthly feature"} icon={<Activity className="w-5 h-5" />} color="purple" />
      </div>

      <Card title="Latest Market News" subtitle={`${latest.length} stories from RSS and market queries`}>
        {latest.length === 0 ? (
          <div className="py-12 text-sm text-slate-500 text-center">No RSS articles available. Run the pipeline to fetch news.</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {latest.map((article) => (
              <a
                key={article.article_id}
                href={article.url}
                target="_blank"
                rel="noreferrer"
                className="group rounded-lg border border-slate-200 bg-slate-950 text-white overflow-hidden hover:border-blue-400 hover:shadow-md transition-all"
              >
                <div className="h-20 bg-gradient-to-br from-slate-800 via-slate-900 to-blue-950" />
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3 text-xs text-slate-400">
                    <span className="font-semibold text-blue-200 truncate">{hostLabel(article.source)}</span>
                    <span className="shrink-0">{timeAgo(article.published_at)}</span>
                  </div>
                  <h3 className="text-sm font-bold leading-snug line-clamp-2 group-hover:text-blue-200">{article.title}</h3>
                  <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">{article.summary || "Open source article for full details."}</p>
                  <div className="flex items-center justify-between pt-1">
                    <div className="flex gap-2">
                      <Badge color={article.is_negative ? "red" : article.sentiment > 0.05 ? "green" : "slate"} size="xs">
                        sentiment {article.sentiment.toFixed(2)}
                      </Badge>
                      {article.risk_event_count > 0 && <Badge color="amber" size="xs">risk {article.risk_event_count}</Badge>}
                    </div>
                    <ExternalLink className="w-4 h-4 text-slate-400 group-hover:text-blue-200" />
                  </div>
                </div>
              </a>
            ))}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Daily News Risk" subtitle="Article count and risk events by fetched publication date">
          <BarChart
            data={daily.slice(-14).map((d) => ({ label: d.date.slice(5), value: d.risk_event_count, color: d.risk_event_count > 5 ? "#ef4444" : "#f59e0b" }))}
            yFormat={(v) => v.toFixed(0)}
            height={280}
          />
        </Card>
        <Card title="News Evidence Table" subtitle="Negative/risk articles that support regime diagnostics">
          <Table
            columns={[
              { key: "time", label: "Time" },
              { key: "source", label: "Source" },
              { key: "title", label: "Headline" },
              { key: "risk", label: "Risk", align: "right" },
              { key: "sentiment", label: "Sent.", align: "right" },
            ]}
            data={riskRows}
            maxHeight="340px"
          />
        </Card>
      </div>
    </div>
  );
}
