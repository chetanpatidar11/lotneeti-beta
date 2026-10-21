export const importFields = [
  "Name", "PAN", "Type", "DPID", "CLIENT ID", "UPI ID", "Account Number", "Bank Name",
] as const;

export type ImageImportRow = Record<(typeof importFields)[number], string>;

export function emptyImageRow(): ImageImportRow {
  return Object.fromEntries(importFields.map((field) => [field, ""])) as ImageImportRow;
}

type Word = { text: string; x: number; y: number; height: number };
type Line = { words: Word[]; y: number; height: number };

function visualLines(tsv: string): Line[] {
  const sourceLines = tsv.split(/\r?\n/);
  const hasHeader = sourceLines[0]?.startsWith("level\t");
  const columns = hasHeader ? sourceLines[0].split("\t") : [
    "level", "page_num", "block_num", "par_num", "line_num", "word_num",
    "left", "top", "width", "height", "conf", "text",
  ];
  const records = hasHeader ? sourceLines.slice(1) : sourceLines;
  const index = (name: string) => columns.indexOf(name);
  if (["level", "left", "top", "height", "text"].some((name) => index(name) < 0)) return [];
  const words: Word[] = [];
  for (const record of records) {
    const cells = record.split("\t");
    if (cells[index("level")] !== "5") continue;
    const text = cells.slice(index("text")).join("\t").trim();
    const x = Number(cells[index("left")]);
    const y = Number(cells[index("top")]);
    const height = Number(cells[index("height")]);
    if (!text || !Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(height)) continue;
    words.push({ text, x, y, height });
  }
  words.sort((a, b) => (a.y + a.height / 2) - (b.y + b.height / 2) || a.x - b.x);
  const lines: Line[] = [];
  for (const word of words) {
    const center = word.y + word.height / 2;
    const last = lines.at(-1);
    if (last && Math.abs(center - last.y) <= Math.max(7, Math.min(last.height, word.height) * 0.55)) {
      last.words.push(word);
      last.y = (last.y * (last.words.length - 1) + center) / last.words.length;
    } else {
      lines.push({ words: [word], y: center, height: word.height });
    }
  }
  for (const line of lines) line.words.sort((a, b) => a.x - b.x);
  return lines;
}

function headerPositions(line: Line): Partial<Record<keyof ImageImportRow, number>> {
  const positions: Partial<Record<keyof ImageImportRow, number>> = {};
  for (const word of line.words) {
    const token = word.text.toUpperCase().replace(/[^A-Z]/g, "");
    const field = token === "NAME" && positions.Name === undefined ? "Name"
      : token === "PAN" ? "PAN" : token === "TYPE" ? "Type"
      : token === "DPID" ? "DPID" : token === "CLIENT" ? "CLIENT ID"
      : token === "UPI" ? "UPI ID" : token === "ACCOUNT" ? "Account Number"
      : token === "BANK" ? "Bank Name" : null;
    if (field) positions[field] = word.x;
  }
  return positions;
}

function tidy(field: keyof ImageImportRow, words: Word[]): string {
  const text = words.map((word) => word.text).join(" ").trim();
  if (field === "UPI ID") return text.replace(/\s*@\s*/g, "@").replace(/\s+/g, "").toLowerCase();
  if (field === "PAN" || field === "CLIENT ID" || field === "DPID" || field === "Account Number") {
    return text.replace(/\s+/g, "").toUpperCase();
  }
  return field === "Type" ? text.toUpperCase() : text;
}

function rowFromColumns(line: Line, starts: Partial<Record<keyof ImageImportRow, number>>): ImageImportRow {
  const row = emptyImageRow();
  const ordered = importFields.filter((field) => starts[field] !== undefined);
  const grouped: Partial<Record<keyof ImageImportRow, Word[]>> = {};
  for (const word of line.words) {
    let field = ordered[0];
    for (let index = 1; index < ordered.length; index += 1) {
      const previous = starts[ordered[index - 1]] ?? 0;
      const next = starts[ordered[index]] ?? 0;
      const boundary = next - Math.max(8, (next - previous) * 0.1);
      if (word.x >= boundary) field = ordered[index];
    }
    if (field) (grouped[field] ??= []).push(word);
  }
  for (const field of importFields) row[field] = tidy(field, grouped[field] ?? []);
  return row;
}

function rowFromPatterns(line: Line): ImageImportRow {
  const row = emptyImageRow();
  const words = line.words;
  const pan = words.findIndex((word) => /^[A-Z]{5}[0-9]{4}[A-Z]$/i.test(word.text));
  const type = words.findIndex((word) => /^(CDSL|NSDL)$/i.test(word.text));
  const upi = words.findIndex((word) => /^[a-z0-9._-]+@[a-z0-9._-]+$/i.test(word.text));
  if (pan < 0 && type < 0 && upi < 0) return row;
  const nameEnd = pan >= 0 ? pan : type >= 0 ? type : upi;
  row.Name = tidy("Name", words.slice(0, nameEnd));
  if (pan >= 0) row.PAN = tidy("PAN", [words[pan]]);
  if (type >= 0) row.Type = tidy("Type", [words[type]]);
  if (upi >= 0) row["UPI ID"] = tidy("UPI ID", [words[upi]]);
  const idStart = type >= 0 ? type + 1 : pan + 1;
  const idEnd = upi >= 0 ? upi : words.length;
  const ids = words.slice(Math.max(idStart, 0), idEnd);
  const clientIndex = ids.findLastIndex((word) => /^[A-Z0-9]{8,16}$/i.test(word.text));
  if (clientIndex >= 0) {
    row["CLIENT ID"] = tidy("CLIENT ID", [ids[clientIndex]]);
    row.DPID = tidy("DPID", ids.slice(0, clientIndex));
  }
  if (upi >= 0) {
    const after = words.slice(upi + 1);
    const accountIndex = after.findIndex((word) => /^[0-9]{6,20}$/.test(word.text));
    if (accountIndex >= 0) {
      row["Account Number"] = after[accountIndex].text;
      row["Bank Name"] = tidy("Bank Name", after.filter((_, index) => index !== accountIndex));
    } else row["Bank Name"] = tidy("Bank Name", after);
  }
  return row;
}

export function rowsFromImageTsv(tsv: string): ImageImportRow[] {
  const lines = visualLines(tsv);
  const header = lines.map((line, index) => ({ index, positions: headerPositions(line) }))
    .find(({ positions }) => ["Name", "PAN", "Type", "CLIENT ID", "UPI ID"]
      .filter((field) => positions[field as keyof ImageImportRow] !== undefined).length >= 4);
  const rows = lines.slice(header ? header.index + 1 : 0).map((line) => {
    const row = header ? rowFromColumns(line, header.positions) : rowFromPatterns(line);
    return row;
  });
  return rows.filter((row) => row.Name && (row.PAN || row.Type || row["UPI ID"]))
    .slice(0, 100);
}
