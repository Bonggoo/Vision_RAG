import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_KR, Source_Serif_4, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import Toaster from "@/components/ui/Toaster";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const notoSansKr = Noto_Sans_KR({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-kr",
});

// 제목 전용 세리프 — 본문 산세리프와 대비를 주되 장식은 최소화
const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "600"],
  variable: "--font-serif",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono-util",
});

export const metadata: Metadata = {
  title: "TechNote",
  description: "AI 기반 산업용 매뉴얼 분석 시스템",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "TechNote",
  },
  icons: {
    icon: "/icon-192x192.png",
    apple: "/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f5" },
    { media: "(prefers-color-scheme: dark)", color: "#262624" },
  ],
  viewportFit: "cover",            // iOS 노치 safe area 대응
  interactiveWidget: "resizes-visual", // 모바일 키보드 올라올 때 레이아웃 유지
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: <head>의 사전 다크모드 스크립트가 SSR 이후 <html>의
    // className을 직접 바꾸므로 hydration mismatch가 정상적으로 발생 → 경고 억제(표준 패턴)
    <html lang="ko" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var savedTheme = localStorage.getItem('theme');
                  var isDark = savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches);
                  if (isDark) {
                    document.documentElement.classList.add('dark');
                  } else {
                    document.documentElement.classList.remove('dark');
                  }
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <body className={`${inter.variable} ${notoSansKr.variable} ${sourceSerif.variable} ${jetBrainsMono.variable} font-sans bg-background text-foreground`}>
        <ServiceWorkerRegister />
        {children}
        <Toaster />
        <ConfirmDialog />
      </body>
    </html>
  );
}

