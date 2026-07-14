import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_KR, Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";
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
  variable: "--font-pretendard", // CSS 변수명은 유지 (Pretendard 대체용)
});

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-display",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
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
  themeColor: "#151218",
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
      <body className={`${inter.variable} ${notoSansKr.variable} ${plusJakartaSans.variable} ${jetBrainsMono.variable} font-sans bg-background text-foreground`}>
        <ServiceWorkerRegister />
        {children}
        <Toaster />
        <ConfirmDialog />
      </body>
    </html>
  );
}

