import { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={[
        "rounded-[var(--radius-card)] bg-[color:var(--surface-400)]",
        "border border-[color:var(--border-10)]",
        "shadow-[var(--shadow-ambient)]",
        "transition-shadow duration-200",
        "hover:shadow-[var(--shadow-card)]",
        className,
      ].join(" ")}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={["px-4 pt-4 pb-2", className].join(" ")}>{children}</div>;
}

export function CardTitle({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={[
        "text-[22px] leading-[1.3] tracking-[-0.11px]",
        "font-[400]",
        className,
      ].join(" ")}
      style={{ fontFamily: "var(--font-display)" }}
    >
      {children}
    </div>
  );
}

export function CardDescription({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={["text-[14px] leading-[1.5] text-[color:var(--muted-fg)]", className].join(" ")}>
      {children}
    </div>
  );
}

export function CardContent({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={["px-4 pb-4", className].join(" ")}>{children}</div>;
}

