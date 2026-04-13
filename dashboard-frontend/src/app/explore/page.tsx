import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { listRunFiles, loadCollection } from "@/lib/ejarn";

export default async function ExplorePage() {
  const runs = await listRunFiles();
  const topRuns = runs.slice(0, 12);
  const collections = (await Promise.all(topRuns.map((r) => loadCollection(r.filePath)))).filter(Boolean) as any[];

  const rows = collections.flatMap((c, idx) => {
    const items = (c.items ?? []) as any[];
    const src = c.source ?? topRuns[idx]?.section ?? "-";
    const run = topRuns[idx];
    return items.slice(0, 8).map((it, itemIdx) => ({
      date: it.date,
      topic: it.topic,
      source: src,
      link: it.link,
      category: (it.category ?? []).join(", "),
      _key: `${run?.yymm ?? "na"}|${run?.section ?? "na"}|${it.link ?? "na"}|${it.date ?? "na"}|${itemIdx}`,
    }));
  });

  return (
    <AppShell title="Explore" subtitle="필터/검색은 다음 단계에서 추가합니다. 현재는 최근 파일 일부를 미리봅니다.">
      <Card>
        <CardHeader>
          <CardTitle>최근 기사 미리보기</CardTitle>
          <CardDescription>
            `result/`에 있는 JSON을 직접 읽어 표시합니다. (대용량 최적화는 FastAPI 단계에서)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto">
            <table className="w-full border-collapse text-[14px]">
              <thead>
                <tr className="border-b border-[color:var(--border-20)]">
                  <th className="text-left py-2 pr-3 font-[500]">date</th>
                  <th className="text-left py-2 pr-3 font-[500]">topic</th>
                  <th className="text-left py-2 pr-3 font-[500]">source</th>
                  <th className="text-left py-2 pr-3 font-[500]">category</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r._key} className="border-b border-[color:var(--border-10)]">
                    <td className="py-2 pr-3 text-[color:var(--muted-fg)] whitespace-nowrap">{r.date}</td>
                    <td className="py-2 pr-3">
                      <a
                        href={r.link}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[color:var(--fg)] hover:text-[color:var(--error)] transition-colors duration-150"
                      >
                        {r.topic}
                      </a>
                    </td>
                    <td className="py-2 pr-3 text-[color:var(--muted-fg)] whitespace-nowrap">{r.source}</td>
                    <td className="py-2 pr-3 text-[color:var(--muted-fg)]">{r.category}</td>
                  </tr>
                ))}
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-6 text-[color:var(--muted-fg)]">
                      표시할 데이터가 없습니다. `result/2604/*.json` 같은 파일이 있는지 확인하세요.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}

