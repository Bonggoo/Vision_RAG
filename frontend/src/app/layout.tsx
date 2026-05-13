import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_KR } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const notoSansKr = Noto_Sans_KR({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-pretendard", // CSS 변수명은 유지 (Pretendard 대체용)
});

export const metadata: Metadata = {
  title: "Vision RAG",
  description: "Agentic Vision RAG for Industrial Manuals",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#1a1f36",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="dark">
      <body className={`${inter.variable} ${notoSansKr.variable} font-sans min-h-screen bg-background text-foreground`}>
        {children}
      </body>
    </html>
  );
}
