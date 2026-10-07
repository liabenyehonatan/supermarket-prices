import type { Metadata } from "next";
import { Assistant, Heebo, DM_Mono } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import { routing } from "@/i18n/routing";
import Header from "@/components/layout/Header";
import "../globals.css";

const assistant = Assistant({
  subsets: ["latin", "hebrew"], weight: ["300", "400", "600", "700"],
  variable: "--font-assistant", display: "swap",
});
const heebo = Heebo({
  subsets: ["latin", "hebrew"], weight: ["400", "700", "800", "900"],
  variable: "--font-heebo", display: "swap",
});
const dmMono = DM_Mono({
  subsets: ["latin"], weight: ["400", "500"],
  variable: "--font-dm-mono", display: "swap",
});

export const metadata: Metadata = {
  title: "Machirista — מחיריסטה",
  description: "השוואת מחירים חכמה בין כל רשתות הסופרמרקט בישראל",
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!routing.locales.includes(locale as "he" | "en")) notFound();
  const messages = await getMessages();
  const isRtl = locale === "he";

  return (
    <html lang={locale} dir={isRtl ? "rtl" : "ltr"}>
      <body className={`${assistant.variable} ${heebo.variable} ${dmMono.variable} font-sans bg-white text-gray-900 antialiased`}>
        <NextIntlClientProvider messages={messages}>
          <div className="min-h-screen flex flex-col">
            <Header locale={locale} />
            <main className="flex-1">{children}</main>
            <footer className="bg-gray-50 border-t border-gray-100 mt-20">
              <div className="max-w-6xl mx-auto px-5 py-10 flex flex-col sm:flex-row items-center justify-between gap-4">
                <span className={`font-bold text-gray-400 ${isRtl ? "font-hebrew text-lg" : "text-lg tracking-tight"}`}>
                  {isRtl ? "מחיריסטה" : "Machirista"}
                </span>
                <span className="text-sm text-gray-400">
                  {isRtl ? "נתונים מתעדכנים כל 3 שעות" : "Prices refresh every 3 hours"} · © 2026
                </span>
              </div>
            </footer>
          </div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
