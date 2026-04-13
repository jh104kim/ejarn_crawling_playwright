import Link from "next/link";
import { ReactNode } from "react";

const nav = [
  { href: "/explore", label: "Explore" },
  { href: "/trends", label: "Trends" },
  { href: "/monthly", label: "Monthly" },
  { href: "/quality", label: "Quality" },
];

export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-full flex flex-col">
      <header className="sticky top-0 z-20 bg-[color:var(--surface-200)]/80 backdrop-blur border-b border-[color:var(--border-10)]">
        <div className="mx-auto max-w-[1200px] px-5 py-4 flex items-center justify-between">
          <div className="flex flex-col">
            <div
              className="text-[26px] leading-[1.25] tracking-[-0.325px]"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {title}
            </div>
            {subtitle ? (
              <div className="text-[14px] leading-[1.35] text-[color:var(--muted-fg)]">
                {subtitle}
              </div>
            ) : null}
          </div>
          <nav className="flex items-center gap-2">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className="rounded-[9999px] px-3 py-[6px] text-[14px] text-[rgba(38,37,30,0.7)] hover:text-[color:var(--error)] transition-colors duration-150"
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto max-w-[1200px] px-5 py-6">{children}</div>
      </main>
    </div>
  );
}

