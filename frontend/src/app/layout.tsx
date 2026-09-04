import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VoiceGuard — Live Voice Clone Detection",
  description: "Real-time AI-powered voice cloning detection dashboard for phone call security.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
