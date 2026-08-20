import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "HelpSystem Carreira",
    template: "%s | HelpSystem Carreira",
  },
  description: "Radar inteligente, candidaturas assistidas e acompanhamento da sua carreira.",
  applicationName: "HelpSystem Carreira",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "HS Carreira",
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: "#07111b",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
