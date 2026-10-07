"use client";

import { useTranslations, useLocale } from "next-intl";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import BasketBuilder from "@/components/basket/BasketBuilder";
import SearchBar from "@/components/search/SearchBar";

export default function HeroSection() {
  const t = useTranslations("hero");
  const locale = useLocale();
  const isRtl = locale === "he";
  const [tab, setTab] = useState<"basket" | "search">("basket");

  return (
    <section className="bg-gray-50">
      <div className="max-w-6xl mx-auto px-5 pt-14 pb-16 md:pt-20 md:pb-24">
        <div className="text-center max-w-2xl mx-auto mb-10">
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className={`text-[clamp(28px,5vw,48px)] leading-[1.15] tracking-tight text-gray-900 mb-4 ${isRtl ? "font-hebrew font-black" : "font-bold"}`}
          >
            {isRtl ? "מצאו את הסופר הזול ביותר" : "Find the cheapest supermarket"}
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1, ease: "easeOut" }}
            className="text-gray-500 text-[15px] leading-relaxed"
          >
            {t("subtitle")}
          </motion.p>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease: "easeOut" }}
          className="max-w-md mx-auto"
        >
          <div className="flex gap-1 mb-4 bg-gray-100 rounded-xl p-1">
            {(["basket", "search"] as const).map((id) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex-1 py-2.5 text-[13px] font-semibold rounded-lg transition-all duration-150 ${
                  tab === id
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                {id === "basket" ? t("basketTab") : t("searchTab")}
              </button>
            ))}
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl p-5 shadow-[0_2px_12px_-4px_rgba(0,0,0,0.06)]">
            <AnimatePresence mode="wait">
              <motion.div
                key={tab}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.15 }}
              >
                {tab === "basket" ? <BasketBuilder /> : <SearchBar />}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
