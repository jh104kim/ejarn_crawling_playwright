import { ReactNode } from "react";

export function Pill({
  children,
  variant = "secondary",
  className = "",
}: {
  children: ReactNode;
  variant?: "secondary" | "active" | "ghost";
  className?: string;
}) {
  const base =
    "inline-flex items-center gap-1 rounded-[var(--radius-pill)] px-2 py-[3px] text-[14px] leading-none transition-colors duration-150";
  const variants: Record<typeof variant, string> = {
    secondary: "bg-[color:var(--surface-400)] text-[rgba(38,37,30,0.6)]",
    active: "bg-[color:var(--surface-500)] text-[rgba(38,37,30,0.6)]",
    ghost: "bg-[rgba(38,37,30,0.06)] text-[rgba(38,37,30,0.55)]",
  };
  return <span className={[base, variants[variant], className].join(" ")}>{children}</span>;
}

