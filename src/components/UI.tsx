import React from "react";
import { TrendingUp, TrendingDown, Minus, Activity, AlertTriangle } from "lucide-react";

export function Card({
  children,
  className = "",
  title,
  subtitle,
  action,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      className={`bg-white rounded-xl border border-slate-200 shadow-sm ${className}`}
    >
      {(title || action) && (
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div>
            {title && (
              <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
            )}
            {subtitle && (
              <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>
            )}
          </div>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

export function StatCard({
  label,
  value,
  subvalue,
  trend,
  icon,
  color = "slate",
}: {
  label: string;
  value: React.ReactNode;
  subvalue?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
  color?: "slate" | "blue" | "green" | "red" | "amber" | "purple";
}) {
  const colorMap: Record<string, string> = {
    slate: "bg-slate-50 text-slate-700",
    blue: "bg-blue-50 text-blue-700",
    green: "bg-emerald-50 text-emerald-700",
    red: "bg-red-50 text-red-700",
    amber: "bg-amber-50 text-amber-700",
    purple: "bg-purple-50 text-purple-700",
  };
  const iconBg: Record<string, string> = {
    slate: "bg-slate-100 text-slate-600",
    blue: "bg-blue-100 text-blue-600",
    green: "bg-emerald-100 text-emerald-600",
    red: "bg-red-100 text-red-600",
    amber: "bg-amber-100 text-amber-600",
    purple: "bg-purple-100 text-purple-600",
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
            {label}
          </p>
          <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
          {subvalue && (
            <p className="text-xs text-slate-500 mt-1">{subvalue}</p>
          )}
        </div>
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center ${iconBg[color]}`}
        >
          {icon || <Activity className="w-5 h-5" />}
        </div>
      </div>
      {trend && (
        <div className="flex items-center gap-1 mt-3">
          {trend === "up" && (
            <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
          )}
          {trend === "down" && (
            <TrendingDown className="w-3.5 h-3.5 text-red-600" />
          )}
          {trend === "neutral" && (
            <Minus className="w-3.5 h-3.5 text-slate-400" />
          )}
        </div>
      )}
    </div>
  );
}

export function Badge({
  children,
  color = "slate",
  size = "sm",
}: {
  children: React.ReactNode;
  color?: "slate" | "blue" | "green" | "red" | "amber" | "purple";
  size?: "xs" | "sm";
}) {
  const colorMap: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700",
    blue: "bg-blue-100 text-blue-700",
    green: "bg-emerald-100 text-emerald-700",
    red: "bg-red-100 text-red-700",
    amber: "bg-amber-100 text-amber-700",
    purple: "bg-purple-100 text-purple-700",
  };
  const sizeMap = { xs: "px-2 py-0.5 text-[10px]", sm: "px-2.5 py-1 text-xs" };
  return (
    <span
      className={`inline-flex items-center font-medium rounded-full ${colorMap[color]} ${sizeMap[size]}`}
    >
      {children}
    </span>
  );
}

export function SignalBadge({ signal }: { signal: string }) {
  const colorMap: Record<string, "green" | "blue" | "amber" | "red" | "slate"> = {
    BUY: "green",
    ADD: "blue",
    HOLD: "slate",
    REDUCE: "amber",
    SELL: "red",
  };
  return <Badge color={colorMap[signal] || "slate"}>{signal}</Badge>;
}

export function RegimeBadge({ regime }: { regime: string }) {
  const colorMap: Record<string, "green" | "red" | "slate" | "blue" | "amber"> = {
    "Bull / Expansion": "green",
    "Bear / Stress": "red",
    "Sideways / Neutral": "slate",
    Recovery: "blue",
    "High Volatility / Risk-Off": "amber",
  };
  return <Badge color={colorMap[regime] || "slate"}>{regime}</Badge>;
}

export function DecisionBadge({ decision }: { decision: string }) {
  const colorMap: Record<string, "blue" | "slate" | "amber"> = {
    REBALANCE: "blue",
    RETAIN: "slate",
    DEFENSIVE: "amber",
  };
  return <Badge color={colorMap[decision] || "slate"}>{decision}</Badge>;
}

interface TableProps {
  columns: { key: string; label: string; align?: "left" | "right" | "center"; width?: string }[];
  data: Record<string, any>[];
  maxHeight?: string;
  rowKey?: (row: Record<string, any>, idx: number) => string;
  onRowClick?: (row: Record<string, any>) => void;
}

export function Table({
  columns,
  data,
  maxHeight = "400px",
  rowKey,
  onRowClick,
}: TableProps) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center text-slate-500 text-sm py-12">
        No data available
      </div>
    );
  }

  return (
    <div className="overflow-auto" style={{ maxHeight }}>
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-slate-50 z-10">
          <tr className="border-b border-slate-200">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-3 py-2.5 font-semibold text-slate-600 text-xs uppercase tracking-wider ${
                  col.align === "right"
                    ? "text-right"
                    : col.align === "center"
                    ? "text-center"
                    : "text-left"
                }`}
                style={col.width ? { width: col.width } : undefined}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr
              key={rowKey ? rowKey(row, idx) : idx}
              className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${
                onRowClick ? "cursor-pointer" : ""
              }`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-3 py-2.5 text-slate-700 ${
                    col.align === "right"
                      ? "text-right tabular-nums"
                      : col.align === "center"
                      ? "text-center"
                      : "text-left"
                  }`}
                >
                  {row[col.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProgressBar({
  value,
  max = 1,
  color = "#3b82f6",
  height = 6,
}: {
  value: number;
  max?: number;
  color?: string;
  height?: number;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div
      className="w-full bg-slate-100 rounded-full overflow-hidden"
      style={{ height }}
    >
      <div
        className="rounded-full transition-all duration-500"
        style={{ width: `${pct}%`, height, background: color }}
      />
    </div>
  );
}

export function LoadingSpinner({ message = "Loading..." }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <div className="w-8 h-8 border-3 border-slate-200 border-t-blue-600 rounded-full animate-spin" />
      <p className="text-sm text-slate-500 mt-3">{message}</p>
    </div>
  );
}

export function EmptyState({
  message = "No data available",
  icon,
}: {
  message?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12">
      {icon || <AlertTriangle className="w-8 h-8 text-slate-300" />}
      <p className="text-sm text-slate-500 mt-2">{message}</p>
    </div>
  );
}
