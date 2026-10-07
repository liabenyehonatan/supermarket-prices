"use client";

import { useTranslations, useLocale } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import BasketIndicator from "@/components/basket/BasketIndicator";

export default function Header({ locale }: { locale: string }) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const isRtl = locale === "he";
  const other = locale === "he" ? "en" : "he";

  const switchLocale = () => {
    const s = pathname.split("/"); s[1] = other;
    router.push(s.join("/") || `/${other}`);
  };

  const links = [
    { href: `/${locale}`, label: t("basket") },
    { href: `/${locale}/search`, label: t("search") },
  ];

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-gray-100 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <div className="max-w-6xl mx-auto px-5 flex items-center justify-between h-[60px]">

        {/* Logo */}
        <Link href={`/${locale}`} className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
            <span className="text-white font-bold text-sm">M</span>
          </div>
          <span className={`font-bold text-gray-900 ${isRtl ? "font-hebrew text-[17px]" : "text-[17px] tracking-tight"}`}>
            {isRtl ? "מחיריסטה" : "Machirista"}
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          {links.map((l) => (
            <Link key={l.href} href={l.href}
              className="px-4 py-2 rounded-lg text-[14px] font-semibold text-gray-500 hover:text-gray-900 hover:bg-gray-50 transition-colors">
              {l.label}
            </Link>
          ))}
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          <BasketIndicator locale={locale} />
          <button onClick={switchLocale}
            className="hidden sm:flex items-center justify-center w-8 h-8 rounded-lg text-xs font-bold text-gray-400 hover:text-gray-700 hover:bg-gray-50 border border-gray-200 transition-colors">
            {locale === "he" ? "EN" : "עב"}
          </button>

          {/* Mobile menu */}
          <button className="md:hidden p-2 -me-2" onClick={() => setMenuOpen(!menuOpen)}>
            <div className="w-5 flex flex-col gap-[5px]">
              {[0, 1, 2].map((i) => (
                <motion.span key={i}
                  animate={menuOpen ? (i === 0 ? { rotate: 45, y: 7 } : i === 1 ? { opacity: 0 } : { rotate: -45, y: -7 }) : { rotate: 0, y: 0, opacity: 1 }}
                  transition={{ duration: 0.15 }}
                  className="block h-[1.5px] bg-gray-600 origin-center" />
              ))}
            </div>
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }}
            transition={{ duration: 0.15 }} className="md:hidden overflow-hidden border-t border-gray-100">
            <div className="px-5 py-3 space-y-1 bg-white">
              {links.map((l) => (
                <Link key={l.href} href={l.href} onClick={() => setMenuOpen(false)}
                  className="block py-2.5 text-sm font-semibold text-gray-600 hover:text-gray-900">{l.label}</Link>
              ))}
              <button onClick={() => { switchLocale(); setMenuOpen(false); }}
                className="block py-2.5 text-sm text-gray-400 hover:text-gray-700">
                {locale === "he" ? "English" : "עברית"}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
