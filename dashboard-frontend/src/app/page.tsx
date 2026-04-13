import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";

export default function Home() {
  return (
    <AppShell
      title="eJARN Insight Dashboard"
      subtitle="result/*.json 및 result/YYMM/*.json을 읽어 월별·태그별 인사이트를 탐색합니다."
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>빠른 시작</CardTitle>
            <CardDescription>
              현재는 파일 기반(로컬)으로 `result/`를 직접 읽어 요약합니다. 추후 FastAPI로 확장할 수 있습니다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <Link
                href="/monthly"
                className="rounded-[8px] bg-[color:var(--surface-300)] px-[14px] py-[10px] text-[14px] leading-none text-[color:var(--fg)] hover:text-[color:var(--error)] transition-colors duration-150"
              >
                월별 보기(2603/2604)
              </Link>
              <Link
                href="/explore"
                className="rounded-[8px] bg-[color:var(--surface-300)] px-[14px] py-[10px] text-[14px] leading-none text-[color:var(--fg)] hover:text-[color:var(--error)] transition-colors duration-150"
              >
                탐색(Explore)
              </Link>
              <Link
                href="/quality"
                className="rounded-[8px] bg-[color:var(--surface-300)] px-[14px] py-[10px] text-[14px] leading-none text-[color:var(--fg)] hover:text-[color:var(--error)] transition-colors duration-150"
              >
                품질(Quality)
              </Link>
            </div>
            <div className="mt-4 text-[17px] leading-[1.35]" style={{ fontFamily: "var(--font-body)" }}>
              따뜻한 크림 배경, 웜블랙 텍스트, oklab 보더, pill 태그, 큰 블러 섀도우. 이 UI는
              프로젝트의 `DESIGN.md` 규칙을 그대로 따릅니다.
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>데이터 신호</CardTitle>
            <CardDescription>오염(404) / 기본값(Unknown 등)을 항상 노출합니다.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <Pill>oklab border</Pill>
              <Pill>cream surface</Pill>
              <Pill variant="active">pill tags</Pill>
              <Pill variant="ghost">ambient shadow</Pill>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
