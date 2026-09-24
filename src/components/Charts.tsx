import React from "react";

interface LineChartProps {
  data: { label: string; values: number[] }[];
  xLabels: string[];
  height?: number;
  yFormat?: (v: number) => string;
  colors?: string[];
  showLegend?: boolean;
}

export function LineChart({
  data,
  xLabels,
  height = 300,
  yFormat = (v) => v.toFixed(2),
  colors,
  showLegend = true,
}: LineChartProps) {
  const width = 800;
  const pad = { top: 20, right: 20, bottom: 40, left: 60 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  if (data.length === 0 || xLabels.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-slate-500 text-sm"
        style={{ height }}
      >
        No data available
      </div>
    );
  }

  const allValues = data.flatMap((d) => d.values).filter((v) => v != null);
  if (allValues.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-slate-500 text-sm"
        style={{ height }}
      >
        No data available
      </div>
    );
  }

  const minY = Math.min(...allValues);
  const maxY = Math.max(...allValues);
  const yRange = maxY - minY || 1;
  const yPad = yRange * 0.1;
  const yMin = minY - yPad;
  const yMax = maxY + yPad;

  const xStep = chartW / Math.max(1, xLabels.length - 1);

  const defaultColors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];
  const chartColors = colors || defaultColors;

  const yTicks = 5;
  const yTickValues = Array.from(
    { length: yTicks + 1 },
    (_, i) => yMin + ((yMax - yMin) * i) / yTicks
  );

  const xTickSkip = Math.max(1, Math.ceil(xLabels.length / 12));

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Grid lines */}
        {yTickValues.map((v, i) => {
          const y = pad.top + chartH - ((v - yMin) / (yMax - yMin)) * chartH;
          return (
            <g key={i}>
              <line
                x1={pad.left}
                y1={y}
                x2={pad.left + chartW}
                y2={y}
                stroke="#e2e8f0"
                strokeWidth={1}
                strokeDasharray="2,2"
              />
              <text
                x={pad.left - 8}
                y={y + 4}
                textAnchor="end"
                className="fill-slate-400 text-[10px]"
              >
                {yFormat(v)}
              </text>
            </g>
          );
        })}

        {/* X axis labels */}
        {xLabels.map((label, i) => {
          if (i % xTickSkip !== 0 && i !== xLabels.length - 1) return null;
          const x = pad.left + i * xStep;
          return (
            <text
              key={i}
              x={x}
              y={pad.top + chartH + 20}
              textAnchor="middle"
              className="fill-slate-400 text-[10px]"
            >
              {label}
            </text>
          );
        })}

        {/* Lines */}
        {data.map((series, si) => {
          const color = chartColors[si % chartColors.length];
          const points = series.values
            .map((v, i) => {
              if (v == null || isNaN(v)) return null;
              const x = pad.left + i * xStep;
              const y =
                pad.top + chartH - ((v - yMin) / (yMax - yMin)) * chartH;
              return `${x},${y}`;
            })
            .filter(Boolean)
            .join(" ");
          return (
            <g key={si}>
              <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </g>
          );
        })}
      </svg>
      {showLegend && (
        <div className="flex flex-wrap gap-4 justify-center mt-2">
          {data.map((series, i) => (
            <div key={i} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-sm"
                style={{ background: chartColors[i % chartColors.length] }}
              />
              <span className="text-xs text-slate-600">{series.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface BarChartProps {
  data: { label: string; value: number; color?: string }[];
  height?: number;
  yFormat?: (v: number) => string;
  horizontal?: boolean;
}

export function BarChart({
  data,
  height = 300,
  yFormat = (v) => v.toFixed(2),
  horizontal = false,
}: BarChartProps) {
  const width = 800;
  const pad = { top: 20, right: 20, bottom: 40, left: 60 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-slate-500 text-sm"
        style={{ height }}
      >
        No data available
      </div>
    );
  }

  const values = data.map((d) => d.value).filter((v) => v != null);
  const minY = Math.min(0, ...values);
  const maxY = Math.max(...values, 0);
  const yRange = maxY - minY || 1;
  const barW = chartW / data.length;
  const zeroY = pad.top + chartH - ((0 - minY) / yRange) * chartH;

  const defaultColors = [
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#06b6d4",
  ];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto"
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Zero line */}
      <line
        x1={pad.left}
        y1={zeroY}
        x2={pad.left + chartW}
        y2={zeroY}
        stroke="#cbd5e1"
        strokeWidth={1}
      />

      {data.map((d, i) => {
        const x = pad.left + i * barW + barW * 0.15;
        const bw = barW * 0.7;
        const valH = ((d.value - 0) / yRange) * chartH;
        const y = d.value >= 0 ? zeroY - valH : zeroY;
        const color = d.color || defaultColors[i % defaultColors.length];
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={Math.abs(valH)} fill={color} rx={2} />
            <text
              x={x + bw / 2}
              y={pad.top + chartH + 18}
              textAnchor="middle"
              className="fill-slate-400 text-[10px]"
            >
              {d.label.length > 12 ? d.label.slice(0, 10) + "…" : d.label}
            </text>
            <text
              x={x + bw / 2}
              y={d.value >= 0 ? y - 5 : y + Math.abs(valH) + 12}
              textAnchor="middle"
              className="fill-slate-500 text-[9px]"
            >
              {yFormat(d.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

interface DonutChartProps {
  data: { label: string; value: number; color?: string }[];
  size?: number;
  centerLabel?: string;
  centerValue?: string;
}

export function DonutChart({
  data,
  size = 200,
  centerLabel,
  centerValue,
}: DonutChartProps) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0 || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-slate-500 text-sm"
        style={{ height: size }}
      >
        No data available
      </div>
    );
  }

  const radius = size / 2 - 10;
  const innerRadius = radius * 0.6;
  const cx = size / 2;
  const cy = size / 2;

  const defaultColors = [
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#06b6d4",
  ];

  let cumAngle = -Math.PI / 2;
  const slices = data.map((d, i) => {
    const angle = (d.value / total) * 2 * Math.PI;
    const startAngle = cumAngle;
    const endAngle = cumAngle + angle;
    cumAngle = endAngle;

    const x1 = cx + radius * Math.cos(startAngle);
    const y1 = cy + radius * Math.sin(startAngle);
    const x2 = cx + radius * Math.cos(endAngle);
    const y2 = cy + radius * Math.sin(endAngle);
    const x3 = cx + innerRadius * Math.cos(endAngle);
    const y3 = cy + innerRadius * Math.sin(endAngle);
    const x4 = cx + innerRadius * Math.cos(startAngle);
    const y4 = cy + innerRadius * Math.sin(startAngle);

    const largeArc = angle > Math.PI ? 1 : 0;
    const path = `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${x4} ${y4} Z`;
    const color = d.color || defaultColors[i % defaultColors.length];

    const midAngle = (startAngle + endAngle) / 2;
    const labelX = cx + (radius + innerRadius) / 2 * Math.cos(midAngle);
    const labelY = cy + (radius + innerRadius) / 2 * Math.sin(midAngle);

    return { path, color, label: d.label, value: d.value, pct: (d.value / total) * 100, labelX, labelY };
  });

  return (
    <div className="flex flex-col items-center">
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        {slices.map((s, i) => (
          <path key={i} d={s.path} fill={s.color} stroke="white" strokeWidth={1} />
        ))}
        {centerLabel && (
          <text x={cx} y={cy - 5} textAnchor="middle" className="fill-slate-700 text-[11px] font-medium">
            {centerLabel}
          </text>
        )}
        {centerValue && (
          <text x={cx} y={cy + 12} textAnchor="middle" className="fill-slate-900 text-[14px] font-bold">
            {centerValue}
          </text>
        )}
      </svg>
      <div className="flex flex-wrap gap-3 justify-center mt-2 max-w-xs">
        {slices.map((s, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} />
            <span className="text-[10px] text-slate-600">
              {s.label} ({s.pct.toFixed(1)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

interface HeatmapProps {
  rows: string[];
  cols: string[];
  values: number[][];
  colorScale?: (v: number) => string;
  cellFormat?: (v: number) => string;
}

export function Heatmap({
  rows,
  cols,
  values,
  colorScale,
  cellFormat = (v) => v.toFixed(2),
}: HeatmapProps) {
  const defaultColorScale = (v: number) => {
    if (v > 0.5) return "#10b981";
    if (v > 0.2) return "#86efac";
    if (v > 0.05) return "#d1fae5";
    if (v > -0.05) return "#f1f5f9";
    if (v > -0.2) return "#fde68a";
    if (v > -0.5) return "#fca5a5";
    return "#ef4444";
  };
  const cs = colorScale || defaultColorScale;

  if (rows.length === 0 || cols.length === 0) {
    return (
      <div className="flex items-center justify-center text-slate-500 text-sm h-32">
        No data available
      </div>
    );
  }

  const cellW = 80;
  const cellH = 40;
  const labelW = 140;
  const labelH = 60;

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${labelW + cols.length * cellW} ${labelH + rows.length * cellH}`}
        className="w-full h-auto"
      >
        {/* Column headers */}
        {cols.map((col, j) => (
          <text
            key={j}
            x={labelW + j * cellW + cellW / 2}
            y={labelH - 8}
            textAnchor="middle"
            className="fill-slate-600 text-[10px] font-medium"
          >
            {col.length > 12 ? col.slice(0, 10) + "…" : col}
          </text>
        ))}
        {/* Row headers */}
        {rows.map((row, i) => (
          <text
            key={i}
            x={labelW - 8}
            y={labelH + i * cellH + cellH / 2 + 4}
            textAnchor="end"
            className="fill-slate-600 text-[10px] font-medium"
          >
            {row.length > 18 ? row.slice(0, 16) + "…" : row}
          </text>
        ))}
        {/* Cells */}
        {values.map((row, i) =>
          row.map((v, j) => {
            const isInvalid = v == null || isNaN(v);
            return (
              <g key={`${i}-${j}`}>
                <rect
                  x={labelW + j * cellW}
                  y={labelH + i * cellH}
                  width={cellW - 2}
                  height={cellH - 2}
                  fill={isInvalid ? "#f1f5f9" : cs(v)}
                  rx={3}
                />
                <text
                  x={labelW + j * cellW + cellW / 2}
                  y={labelH + i * cellH + cellH / 2 + 4}
                  textAnchor="middle"
                  className="fill-slate-700 text-[10px] font-medium"
                >
                  {isInvalid ? "—" : cellFormat(v)}
                </text>
              </g>
            );
          })
        )}
      </svg>
    </div>
  );
}

interface ScatterChartProps {
  data: { x: number; y: number; label?: string; color?: string }[];
  xLabel?: string;
  yLabel?: string;
  height?: number;
}

export function ScatterChart({
  data,
  xLabel = "",
  yLabel = "",
  height = 300,
}: ScatterChartProps) {
  const width = 800;
  const pad = { top: 20, right: 20, bottom: 40, left: 60 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-slate-500 text-sm"
        style={{ height }}
      >
        No data available
      </div>
    );
  }

  const xs = data.map((d) => d.x);
  const ys = data.map((d) => d.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const xRange = maxX - minX || 1;
  const yRange = maxY - minY || 1;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
      {data.map((d, i) => {
        const x = pad.left + ((d.x - minX) / xRange) * chartW;
        const y = pad.top + chartH - ((d.y - minY) / yRange) * chartH;
        return (
          <g key={i}>
            <circle cx={x} cy={y} r={4} fill={d.color || "#3b82f6"} opacity={0.7} />
            {d.label && (
              <text x={x + 6} y={y + 3} className="fill-slate-500 text-[9px]">
                {d.label}
              </text>
            )}
          </g>
        );
      })}
      {xLabel && (
        <text x={pad.left + chartW / 2} y={height - 5} textAnchor="middle" className="fill-slate-500 text-[11px]">
          {xLabel}
        </text>
      )}
      {yLabel && (
        <text
          x={15}
          y={pad.top + chartH / 2}
          textAnchor="middle"
          transform={`rotate(-90 15 ${pad.top + chartH / 2})`}
          className="fill-slate-500 text-[11px]"
        >
          {yLabel}
        </text>
      )}
    </svg>
  );
}

interface StackedAreaProps {
  data: { label: string; values: number[] }[];
  xLabels: string[];
  height?: number;
  colors?: string[];
}

export function StackedAreaChart({
  data,
  xLabels,
  height = 300,
  colors,
}: StackedAreaProps) {
  const width = 800;
  const pad = { top: 20, right: 20, bottom: 40, left: 60 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  if (data.length === 0 || xLabels.length === 0) {
    return (
      <div className="flex items-center justify-center text-slate-500 text-sm" style={{ height }}>
        No data available
      </div>
    );
  }

  const n = xLabels.length;
  const stacked: number[][] = [];
  let cum = new Array(n).fill(0);
  for (const series of data) {
    const layer = series.values.map((v, i) => cum[i] + (v || 0));
    stacked.push([...cum]);
    stacked.push(layer);
    cum = layer;
  }
  const maxY = cum.reduce((a, b) => Math.max(a, b), 0) || 1;
  const xStep = chartW / Math.max(1, n - 1);
  const defaultColors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];
  const chartColors = colors || defaultColors;

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
        {/* Y axis */}
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
          const y = pad.top + chartH - p * chartH;
          return (
            <g key={i}>
              <line x1={pad.left} y1={y} x2={pad.left + chartW} y2={y} stroke="#e2e8f0" strokeWidth={1} strokeDasharray="2,2" />
              <text x={pad.left - 8} y={y + 4} textAnchor="end" className="fill-slate-400 text-[10px]">
                {(p * maxY).toFixed(2)}
              </text>
            </g>
          );
        })}
        {/* X labels */}
        {xLabels.map((label, i) => {
          if (i % Math.max(1, Math.ceil(n / 12)) !== 0 && i !== n - 1) return null;
          return (
            <text key={i} x={pad.left + i * xStep} y={pad.top + chartH + 20} textAnchor="middle" className="fill-slate-400 text-[10px]">
              {label}
            </text>
          );
        })}
        {/* Areas */}
        {data.map((series, si) => {
          const bottom = stacked[si * 2];
          const top = stacked[si * 2 + 1];
          const color = chartColors[si % chartColors.length];
          const topPts = top.map((v, i) => `${pad.left + i * xStep},${pad.top + chartH - (v / maxY) * chartH}`);
          const botPts = bottom.map((v, i) => `${pad.left + i * xStep},${pad.top + chartH - (v / maxY) * chartH}`).reverse();
          const path = `M ${topPts.join(" L ")} L ${botPts.join(" L ")} Z`;
          return <path key={si} d={path} fill={color} opacity={0.75} stroke={color} strokeWidth={1} />;
        })}
      </svg>
      <div className="flex flex-wrap gap-4 justify-center mt-2">
        {data.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-sm" style={{ background: chartColors[i % chartColors.length] }} />
            <span className="text-xs text-slate-600">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
