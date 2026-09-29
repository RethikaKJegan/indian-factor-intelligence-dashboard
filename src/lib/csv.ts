/**
 * Client-side CSV export.
 *
 * Values are quoted and embedded quotes doubled, so a reason string or a
 * company name containing a comma or a quote cannot corrupt the file. A UTF-8
 * BOM is included because Excel otherwise misreads non-ASCII characters.
 */

function escapeCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = typeof value === "string" ? value : String(value);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export interface CsvColumn<T> {
  key: string;
  label?: string;
  /** Maps a row to the value for this column. Defaults to `row[key]`. */
  get?: (row: T) => unknown;
}

/** Reads a named field from a row without requiring an index signature. */
function readField<T>(row: T, key: string): unknown {
  if (row !== null && typeof row === "object" && key in (row as object)) {
    return (row as Record<string, unknown>)[key];
  }
  return undefined;
}

export function toCsv<T>(
  rows: T[],
  columns: CsvColumn<T>[],
  includeHeader = true
): string {
  const lines: string[] = [];
  if (includeHeader) {
    lines.push(columns.map((c) => escapeCell(c.label ?? c.key)).join(","));
  }
  for (const row of rows) {
    lines.push(
      columns
        .map((c) => escapeCell(c.get ? c.get(row) : readField(row, c.key)))
        .join(",")
    );
  }
  // Trailing newline so the file ends cleanly in Excel and `wc -l`.
  return lines.join("\r\n") + "\r\n";
}

export function downloadCsv<T>(
  filename: string,
  rows: T[],
  columns: CsvColumn<T>[]
): void {
  const csv = toCsv(rows, columns);
  // Blob rather than a data: URL so large exports do not hit URL length limits.
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Release the object URL once the download has been handed to the browser.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
