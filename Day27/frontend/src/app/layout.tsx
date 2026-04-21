import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LLM Chat",
  description: "Chat UI for ProxyAPI and local LLM providers"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

