import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PACE — Running Coach",
  description: "나의 기록을 이해하고, 다음 달리기를 계획하세요.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "PACE" },
  icons: { icon: "/icon.svg", apple: "/icon-192.png" }
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#f4f6f3" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko"><body>{children}</body></html>;
}
