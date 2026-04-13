import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { computeMonthlySnapshot, listRunFiles } from "@/lib/ejarn";

export default async function MonthlyPage({
  searchParams,
}: {
  searchParams: Promise<{ yymm?: string }>;
}) {
  const sp = await searchParams;
  const runs = await listRunFiles();
  const months = Array.from(new Set(runs.map((r) => r.yymm))).sort((a, b) => b.localeCompare(a));
  const yymm = sp.yymm && months.includes(sp.yymm) ? sp.yymm : months[0];

  const snapshot = yymm ? await computeMonthlySnapshot(yymm) : null;

  return (
    <AppShell title="Monthly" subtitle="2603/2604 같은 월(YYMM) 기준으로 집계·요약합니다.">
      <div className="flex flex-wrap gap-2 mb-4">
        {months.map((m) => (
          <Link key={m} href={`/monthly?yymm=${m}`}>
            <Pill variant={m === yymm ? "active" : "secondary"}>{m}</Pill>
          </Link>
        ))}
      </div>

      {!snapshot ? (
        <Card>
          <CardHeader>
            <CardTitle>월 데이터 없음</CardTitle>
            <CardDescription>`result/YYMM/*.json` 또는 `*_YYMM.json` 파일이 필요합니다.</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>{snapshot.yymm} 월간 브리프</CardTitle>
              <CardDescription>규칙 기반(LLM 없이)으로 월간 요약을 구성합니다.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="list-disc pl-5 space-y-2 text-[17px] leading-[1.35] text-[color:var(--fg)]" style={{ fontFamily: "var(--font-body)" }}>
                {snapshot.brief.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>

              <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3">
                {snapshot.brief.representative.map((r, idx) => (
                  <div
                    key={`${snapshot.yymm}|${r.link}|${r.date ?? "na"}|${idx}`}
                    className="rounded-[8px] bg-[color:var(--surface-100)] border border-[color:var(--border-10)] p-3"
                  >
                    <div className="text-[11px] tracking-[0.048px] uppercase text-[rgba(38,37,30,0.55)]">
                      {r.date || snapshot.yymm}
                    </div>
                    <a
                      href={r.link}
                      className="block mt-1 text-[16px] leading-[1.5] text-[color:var(--fg)] hover:text-[color:var(--error)] transition-colors duration-150"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {r.topic}
                    </a>
                    <div className="mt-2 text-[14px] leading-[1.5] text-[color:var(--muted-fg)]">
                      {r.summary}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>KPI</CardTitle>
              <CardDescription>월별 규모/품질/태그 다양성</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                <Kpi label="기사" value={`${snapshot.totalItems}`} />
                <Kpi label="파일" value={`${snapshot.monthRuns.length}`} />
                <Kpi label="404 의심" value={`${snapshot.quality.notFound}`} />
                <Kpi label="기본값" value={`${snapshot.quality.defaults}`} />
              </div>

              <div className="mt-4">
                <div className="text-[11px] tracking-[0.048px] uppercase text-[rgba(38,37,30,0.55)]">
                  Unique tags
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Pill>company {snapshot.uniqueTagCounts.company}</Pill>
                  <Pill>category {snapshot.uniqueTagCounts.category}</Pill>
                  <Pill>product {snapshot.uniqueTagCounts.product_type}</Pill>
                  <Pill>refrigerant {snapshot.uniqueTagCounts.refrigerant}</Pill>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="lg:col-span-3">
            <CardHeader>
              <CardTitle>TopN</CardTitle>
              <CardDescription>월별 상위 태그(빈도)</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <TopList title="Company" items={snapshot.top.company} />
                <TopList title="Category" items={snapshot.top.category} />
                <TopList title="Product" items={snapshot.top.product_type} />
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </AppShell>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] bg-[color:var(--surface-100)] border border-[color:var(--border-10)] p-3">
      <div className="text-[11px] tracking-[0.048px] uppercase text-[rgba(38,37,30,0.55)]">
        {label}
      </div>
      <div className="mt-1 text-[22px] tracking-[-0.11px]" style={{ fontFamily: "var(--font-display)" }}>
        {value}
      </div>
    </div>
  );
}

function TopList({ title, items }: { title: string; items: { label: string; count: number }[] }) {
  return (
    <div>
      <div className="text-[11px] tracking-[0.048px] uppercase text-[rgba(38,37,30,0.55)]">
        {title}
      </div>
      <div className="mt-2 space-y-2">
        {items.slice(0, 10).map((it) => (
          <div
            key={it.label}
            className="flex items-center justify-between rounded-[8px] bg-[color:var(--surface-100)] border border-[color:var(--border-10)] px-3 py-2"
          >
            <div className="text-[14px] text-[color:var(--fg)]">{it.label}</div>
            <Pill variant="ghost">{it.count}</Pill>
          </div>
        ))}
        {items.length === 0 ? (
          <div className="text-[14px] text-[color:var(--muted-fg)]">데이터 없음</div>
        ) : null}
      </div>
    </div>
  );
}

