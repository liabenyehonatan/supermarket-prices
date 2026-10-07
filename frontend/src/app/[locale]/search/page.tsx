"use client";

import { useTranslations, useLocale } from "next-intl";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { searchProducts, Product } from "@/lib/api";
import { useBasket } from "@/lib/basket-store";
import { Input } from "@/components/ui/input";
import Image from "next/image";

export default function SearchPage() {
  const t = useTranslations("hero");
  const tP = useTranslations("product");
  const tC = useTranslations("common");
  const locale = useLocale();
  const isRtl = locale === "he";
  const router = useRouter();
  const { addItem } = useBasket();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  const handleSearch = (q: string) => {
    setQuery(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) { setResults([]); setSearched(false); return; }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      const res = await searchProducts(q, 50);
      setResults(res);
      setSearched(true);
      setLoading(false);
    }, 300);
  };

  return (
    <div className="max-w-3xl mx-auto px-5 py-10">
      <h1 className={`text-2xl text-gray-900 mb-6 ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
        {t("searchTab")}
      </h1>

      <div className="relative mb-8">
        <Input
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder={t("searchPlaceholder")}
          dir="auto"
          className="text-base py-3.5"
        />
        {loading && (
          <div className="absolute end-4 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-gray-200 border-t-brand-500 rounded-full animate-spin" />
          </div>
        )}
      </div>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="text-center py-16 text-gray-400 text-sm">
            {tC("loading")}
          </motion.div>
        ) : searched && results.length === 0 ? (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="text-center py-16 text-gray-400 text-sm">
            {tC("notFound")}
          </motion.div>
        ) : results.length > 0 ? (
          <motion.div key="results" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <p className="text-xs text-gray-400 mb-4">{results.length} {isRtl ? "תוצאות" : "results"}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {results.map((p, i) => (
                <motion.div
                  key={p.barcode}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.2 }}
                  onClick={() => router.push(`/${locale}/product/${p.barcode}`)}
                  className="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all"
                >
                  <div className="w-12 h-12 rounded-lg bg-gray-100 flex-shrink-0 overflow-hidden flex items-center justify-center">
                    {p.image_url ? (
                      <Image src={p.image_url} alt={p.name} width={48} height={48}
                        className="object-contain w-full h-full"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                    ) : (
                      <span className="text-[9px] text-gray-300">N/A</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 truncate">{p.name}</p>
                    {p.brand && <p className="text-[11px] text-gray-400 mt-0.5">{p.brand}</p>}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); addItem({ barcode: p.barcode, name: p.name, brand: p.brand, imageUrl: p.image_url }); }}
                    className="flex-shrink-0 w-8 h-8 rounded-lg bg-brand-600 hover:bg-brand-700 text-white flex items-center justify-center transition-colors"
                    title={tP("addToBasket")}
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                  </button>
                </motion.div>
              ))}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
