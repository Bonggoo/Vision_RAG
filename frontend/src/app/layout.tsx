import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_KR } from "next/font/google";
import "./globals.css";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";

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
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Vision RAG",
  },
  icons: {
    icon: "/icon-192x192.png",
    apple: "/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#1a1f36",
  viewportFit: "cover",            // iOS 노치 safe area 대응
  interactiveWidget: "resizes-visual", // 모바일 키보드 올라올 때 레이아웃 유지
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  // 💡 브라우저 환경 검증 + 안전한 localStorage 접근
                  if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
                    var savedTheme = localStorage.getItem('theme');
                    var isDark = savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches);
                    if (isDark) {
                      document.documentElement.classList.add('dark');
                    } else {
                      document.documentElement.classList.remove('dark');
                    }
                  }
                } catch (e) {
                  console.error('Theme initialization error:', e);
                }
              })();
            `,
          }}
        />
      </head>
      <body className={`${inter.variable} ${notoSansKr.variable} font-sans bg-background text-foreground`}>
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
