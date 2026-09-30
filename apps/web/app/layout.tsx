import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Sidebar } from "@/components/Sidebar";
import { PlayerBar } from "@/components/player/PlayerBar";

import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Cueflow",
  description: "DJ library, analysis and cue points for Rekordbox",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="h-full overflow-hidden bg-background text-foreground">
        <Providers>
          <div className="grid h-full grid-cols-[13rem_minmax(0,1fr)] grid-rows-[minmax(0,1fr)_auto]">
            <Sidebar />
            <main className="min-h-0 overflow-hidden">{children}</main>
            <div className="col-span-2">
              <PlayerBar />
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
