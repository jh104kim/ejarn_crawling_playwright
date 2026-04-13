import fs from "node:fs/promises";
import path from "node:path";

export type ArticleItem = {
  date: string;
  topic: string;
  summary: string;
  link: string;
  source_topic?: string;
  source_topic_url?: string;
  related_titles?: string[];
  company?: string[];
  related_comp?: string[];
  product_type?: string[];
  market_segment?: string[];
  refrigerant?: string[];
  application?: string[];
  technology?: string[];
  category?: string[];
};

export type ArticleCollection = {
  source: string;
  collected_at: string;
  items: ArticleItem[];
};

export type RunFile = {
  filePath: string;
  fileName: string;
  yymm: string;
  section: string;
};

const REPO_ROOT = path.resolve(process.cwd(), "..");
const RESULT_ROOT = path.join(REPO_ROOT, "result");

function extractYymmFromPath(p: string): string | null {
  const normalized = p.replaceAll("\\", "/");
  const parts = normalized.split("/");
  const resultIdx = parts.lastIndexOf("result");
  if (resultIdx >= 0 && parts.length > resultIdx + 1) {
    const maybe = parts[resultIdx + 1];
    if (/^\d{4}$/.test(maybe)) return maybe;
  }
  const m = normalized.match(/_(\d{4})\.json$/);
  return m?.[1] ?? null;
}

function extractSectionFromFileName(name: string): string {
  return name.replace(/_\d{4}\.json$/i, "").replace(/\.json$/i, "");
}

async function walkJsonFiles(dir: string): Promise<string[]> {
  const out: string[] = [];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      // Skip common noise
      if (e.name === "node_modules" || e.name === ".next" || e.name === ".venv") continue;
      out.push(...(await walkJsonFiles(p)));
      continue;
    }
    if (e.isFile() && e.name.toLowerCase().endsWith(".json")) out.push(p);
  }
  return out;
}

export async function listRunFiles(): Promise<RunFile[]> {
  const all = await walkJsonFiles(RESULT_ROOT);
  const runs: RunFile[] = [];
  for (const filePath of all) {
    const fileName = path.basename(filePath);
    const yymm = extractYymmFromPath(filePath);
    if (!yymm) continue;
    const section = extractSectionFromFileName(fileName);
    runs.push({ filePath, fileName, yymm, section });
  }
  runs.sort((a, b) => (a.yymm === b.yymm ? a.fileName.localeCompare(b.fileName) : b.yymm.localeCompare(a.yymm)));
  return runs;
}

export async function loadCollection(filePath: string): Promise<ArticleCollection | null> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return null;
    if (!Array.isArray((data as any).items)) return null;
    return data as ArticleCollection;
  } catch {
    return null;
  }
}

function uniq<T>(arr: T[]): T[] {
  return Array.from(new Set(arr));
}

function flattenTags(items: ArticleItem[], key: keyof ArticleItem): string[] {
  const out: string[] = [];
  for (const it of items) {
    const v = it[key];
    if (Array.isArray(v)) out.push(...v.map((s) => String(s)));
  }
  return out;
}

export function computeQualityFlags(items: ArticleItem[]) {
  let notFound = 0;
  let emptySummary = 0;
  let defaults = 0;

  for (const it of items) {
    const summary = (it.summary ?? "").toString();
    const topic = (it.topic ?? "").toString();

    if (!summary.trim()) emptySummary += 1;
    if (/404/i.test(summary) || /^eJARN\.com$/i.test(topic)) notFound += 1;

    const refrigerant = (it.refrigerant ?? []) as string[];
    const application = (it.application ?? []) as string[];
    const category = (it.category ?? []) as string[];
    if (refrigerant.includes("Unknown") || application.includes("Multi-purpose") || category.includes("Market")) defaults += 1;
  }

  return { notFound, emptySummary, defaults };
}

export async function computeMonthlySnapshot(yymm: string) {
  const runs = await listRunFiles();
  const monthRuns = runs.filter((r) => r.yymm === yymm);
  const collections = (await Promise.all(monthRuns.map((r) => loadCollection(r.filePath)))).filter(Boolean) as ArticleCollection[];

  const allItems = collections.flatMap((c) => c.items ?? []);
  const quality = computeQualityFlags(allItems);

  const tags = {
    company: flattenTags(allItems, "company"),
    category: flattenTags(allItems, "category"),
    product_type: flattenTags(allItems, "product_type"),
    market_segment: flattenTags(allItems, "market_segment"),
    refrigerant: flattenTags(allItems, "refrigerant"),
    application: flattenTags(allItems, "application"),
    technology: flattenTags(allItems, "technology"),
  };

  const counts = Object.fromEntries(
    Object.entries(tags).map(([k, vals]) => [k, uniq(vals.filter(Boolean)).length]),
  ) as Record<keyof typeof tags, number>;

  function topN(values: string[], n = 10) {
    const m = new Map<string, number>();
    for (const v of values) {
      const key = (v || "").trim();
      if (!key) continue;
      m.set(key, (m.get(key) ?? 0) + 1);
    }
    return Array.from(m.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, n)
      .map(([label, count]) => ({ label, count }));
  }

  const top = {
    company: topN(tags.company),
    category: topN(tags.category),
    product_type: topN(tags.product_type),
    refrigerant: topN(tags.refrigerant),
    technology: topN(tags.technology),
  };

  // Rule-based monthly brief: top tags + representative articles.
  const representative = allItems
    .filter((it) => (it.summary ?? "").trim() && !/404/i.test(it.summary ?? ""))
    .slice(0, 8)
    .map((it) => ({ topic: it.topic, link: it.link, date: it.date, summary: it.summary }));

  const brief = {
    bullets: [
      `총 ${allItems.length}건 수집 (섹션 파일 ${monthRuns.length}개)`,
      `품질 경고: 404 의심 ${quality.notFound}건 · 빈 요약 ${quality.emptySummary}건 · 기본값 포함 ${quality.defaults}건`,
      `상위 카테고리: ${top.category.slice(0, 5).map((x) => `${x.label}(${x.count})`).join(", ") || "-"}`,
      `상위 제품군: ${top.product_type.slice(0, 5).map((x) => `${x.label}(${x.count})`).join(", ") || "-"}`,
      `상위 냉매: ${top.refrigerant.slice(0, 5).map((x) => `${x.label}(${x.count})`).join(", ") || "-"}`,
    ],
    representative,
  };

  return {
    yymm,
    monthRuns,
    totalItems: allItems.length,
    uniqueTagCounts: counts,
    quality,
    top,
    brief,
  };
}

