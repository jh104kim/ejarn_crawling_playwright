import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { listRunFiles, loadCollection, computeQualityFlags } from "@/lib/ejarn";

export default async function QualityPage() {
  const runs = await listRunFiles();
  const months = Array.from(new Set(runs.map((r) => r.yymm))).sort((a, b) => b.localeCompare(a));
  const month = months[0];
  const monthRuns = runs.filter((r) => r.yymm === month);
  const collections = (await Promise.all(monthRuns.map((r) => loadCollection(r.filePath)))).filter(Boolean) as any[];
  const items = collections.flatMap((c) => c.items ?? []);
  const q = computeQualityFlags(items);

  const perFile = await Promise.all(
    monthRuns.map(async (r) => {
      const c = await loadCollection(r.filePath);
      const it = c?.items ?? [];
      const qq = computeQualityFlags(it);
      return {
        file: r.fileName,
        section: r.section,
        total: it.length,
        notFound: qq.notFound,
        defaults: qq.defaults,
      };
    }),
  );

  return (
    <AppShell title="Quality" subtitle="404/기본값/빈 요약 같은 오염 신호를 빠르게 발견합니다.">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>현재 월(최신) 요약</CardTitle>
            <CardDescription>{month} 기준</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <Pill variant="active">404 의심 {q.notFound}</Pill>
              <Pill variant="secondary">빈 요약 {q.emptySummary}</Pill>
              <Pill variant="secondary">기본값 {q.defaults}</Pill>
            </div>
            <div className="mt-4 text-[14px] leading-[1.5] text-[color:var(--muted-fg)]">
              `Report_*`에서 404가 섞이는 경우가 있어, 이 페이지에서 빠르게 감지하도록 설계했습니다.
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>파일별 품질</CardTitle>
            <CardDescription>월 폴더 내 JSON 단위</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto">
              <table className="w-full border-collapse text-[14px]">
                <thead>
                  <tr className="border-b border-[color:var(--border-20)]">
                    <th className="text-left py-2 pr-3 font-[500]">file</th>
                    <th className="text-left py-2 pr-3 font-[500]">total</th>
                    <th className="text-left py-2 pr-3 font-[500]">404</th>
                    <th className="text-left py-2 pr-3 font-[500]">defaults</th>
                  </tr>
                </thead>
                <tbody>
                  {perFile.map((r) => (
                    <tr key={r.file} className="border-b border-[color:var(--border-10)]">
                      <td className="py-2 pr-3">
                        <div className="text-[color:var(--fg)]">{r.file}</div>
                        <div className="text-[11px] text-[color:var(--muted-fg)]">{r.section}</div>
                      </td>
                      <td className="py-2 pr-3 text-[color:var(--muted-fg)]">{r.total}</td>
                      <td className="py-2 pr-3">
                        <Pill variant={r.notFound > 0 ? "active" : "ghost"}>{r.notFound}</Pill>
                      </td>
                      <td className="py-2 pr-3">
                        <Pill variant={r.defaults > 0 ? "secondary" : "ghost"}>{r.defaults}</Pill>
                      </td>
                    </tr>
                  ))}
                  {perFile.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-6 text-[color:var(--muted-fg)]">
                        표시할 데이터가 없습니다.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

