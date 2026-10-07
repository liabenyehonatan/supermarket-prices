"use client";

import { useTranslations, useLocale } from "next-intl";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { searchProducts, Product } from "@/lib/api";
import { useBasket } from "@/lib/basket-store";
import { Input } from "@/components/ui/input";
import ProductCard from "@/components/search/ProductCard";

export default function SearchBar() {
  const t = useTranslations("hero");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const { addItem } = useBasket();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  const handleSearch = (q: string) => {
    setQuery(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) { setResults([]); return; }
    debounceRef.current = setTimeout(async () => { setLoading(true); setResults(await searchProducts(q)); setLoading(false); }, 300);
  };

  return (
    <div className="relative">
      <div className="relative">
        <Input value={query} onChange={(e) => handleSearch(e.target.value)}
          onFocus={() => setFocused(true)} onBlur={() => setTimeout(() => setFocused(false), 200)}
          placeholder={t("searchPlaceholder")} dir="auto" />
        {loading && (
          <div className="absolute end-4 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-gray-200 border-t-brand-500 rounded-full animate-spin" />
          </div>
        )}
      </div>

      <AnimatePresence>
        {focused && results.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.12 }}
            className="absolute top-full start-0 end-0 mt-1.5 bg-white border border-gray-200 rounded-xl overflow-hidden z-50 shadow-[0_8px_24px_-6px_rgba(0,0,0,0.1)] max-h-80 overflow-y-auto">
            {results.map((p) => (
              <ProductCard key={p.barcode} product={p}
                onAdd={() => addItem({ barcode: p.barcode, name: p.name, brand: p.brand, imageUrl: p.image_url })}
                onClick={() => router.push(`/${locale}/product/${p.barcode}`)} />
            ))}
          </motion.div>
        )}
        {focused && query && !loading && results.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="absolute top-full start-0 end-0 mt-1.5 bg-white border border-gray-200 rounded-xl p-5 text-center text-gray-400 text-sm z-50">
            {tCommon("notFound")}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
