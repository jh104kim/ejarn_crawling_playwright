import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "eJARN Insight Dashboard",
  description: "eJARN 결과 JSON 기반 인사이트 대시보드",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
