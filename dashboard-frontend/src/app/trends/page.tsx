import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { listRunFiles } from "@/lib/ejarn";

export default async function TrendsPage() {
  const runs = await listRunFiles();
  const months = Array.from(new Set(runs.map((r) => r.yymm))).sort((a, b) => a.localeCompare(b));

  // Simple timeseries: number of run files per month (placeholder for article-count timeseries)
  const series = months.map((m) => ({
    yymm: m,
    files: runs.filter((r) => r.yymm === m).length,
  }));

  const max = Math.max(1, ...series.map((s) => s.files));

  return (
    <AppShell title="Trends" subtitle="MVP 단계에서는 월별 파일 수/기사 수 추이부터 시작합니다.">
      <Card>
        <CardHeader>
          <CardTitle>월별 수집 파일 수</CardTitle>
          <CardDescription>추후: 기사 수/태그 비중/증감까지 확장</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {series.map((s) => (
              <div key={s.yymm} className="flex items-center gap-3">
                <div className="w-14 text-[11px] text-[color:var(--muted-fg)]">{s.yymm}</div>
                <div className="flex-1 h-8 rounded-[8px] bg-[color:var(--surface-100)] border border-[color:var(--border-10)] overflow-hidden">
                  <div
                    className="h-full bg-[color:var(--surface-500)]"
                    style={{ width: `${Math.round((s.files / max) * 100)}%` }}
                  />
                </div>
                <div className="w-10 text-right text-[14px] text-[color:var(--fg)]">{s.files}</div>
              </div>
            ))}
            {series.length === 0 ? (
              <div className="py-6 text-[14px] text-[color:var(--muted-fg)]">
                데이터가 없습니다. `result/2604/*.json` 같은 파일이 있는지 확인하세요.
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}

