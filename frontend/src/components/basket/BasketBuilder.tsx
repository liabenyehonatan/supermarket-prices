"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useBasket } from "@/lib/basket-store";
import { compareBasket, BasketCompareResponse, searchProducts, Product } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import BasketResults from "./BasketResults";

export default function BasketBuilder() {
  const t = useTranslations("basket");
  const tHero = useTranslations("hero");
  const tCommon = useTranslations("common");
  const { items, addItem, removeItem, updateQuantity, clearBasket } = useBasket();

  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Product[]>([]);
  const [comparing, setComparing] = useState(false);
  const [results, setResults] = useState<BasketCompareResponse | null>(null);
  const [debounce, setDebounce] = useState<ReturnType<typeof setTimeout>>();

  const handleSearch = (q: string) => {
    setQuery(q);
    if (debounce) clearTimeout(debounce);
    if (!q.trim()) { setSuggestions([]); return; }
    setDebounce(setTimeout(async () => setSuggestions(await searchProducts(q, 6)), 300));
  };

  const handleCompare = async () => {
    if (!items.length) return;
    setComparing(true); setResults(null);
    const res = await compareBasket(items.map((i) => ({ barcode: i.barcode, quantity: i.quantity })));
    setResults(res); setComparing(false);
  };

  return (
    <div className="space-y-3">
      <div className="relative">
        <Input value={query} onChange={(e) => handleSearch(e.target.value)} placeholder={tHero("basketPlaceholder")} dir="auto" />
        <AnimatePresence>
          {suggestions.length > 0 && query && (
            <motion.div
              initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.12 }}
              className="absolute top-full start-0 end-0 mt-1.5 bg-white border border-gray-200 rounded-xl overflow-hidden z-50 shadow-[0_8px_24px_-6px_rgba(0,0,0,0.1)]"
            >
              {suggestions.map((p) => (
                <div
                  key={p.barcode}
                  onClick={() => { addItem({ barcode: p.barcode, name: p.name, brand: p.brand, imageUrl: p.image_url }); setQuery(""); setSuggestions([]); }}
                  className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-gray-50 border-b border-gray-100 last:border-0 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 truncate">{p.name}</p>
                    {p.brand && <p className="text-[11px] text-gray-400">{p.brand}</p>}
                  </div>
                  <span className="text-[11px] font-semibold text-brand-600 flex-shrink-0">+ add</span>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence initial={false}>
        {items.length > 0 ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="border border-gray-200 rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
              <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">{items.length} {t("items")}</span>
              <button onClick={clearBasket} className="text-[11px] font-semibold text-gray-400 hover:text-gray-700 transition-colors uppercase tracking-wide">{t("clear")}</button>
            </div>
            <div className="max-h-40 overflow-y-auto divide-y divide-gray-100">
              {items.map((item) => (
                <div key={item.barcode} className="flex items-center gap-3 px-4 py-2">
                  <span className="flex-1 text-sm text-gray-900 truncate">{item.name}</span>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => updateQuantity(item.barcode, item.quantity - 1)}
                      className="w-6 h-6 rounded bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-mono flex items-center justify-center transition-colors">{"−"}</button>
                    <span className="font-mono text-sm text-gray-900 w-5 text-center tabular-nums">{item.quantity}</span>
                    <button onClick={() => updateQuantity(item.barcode, item.quantity + 1)}
                      className="w-6 h-6 rounded bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-mono flex items-center justify-center transition-colors">+</button>
                    <button onClick={() => removeItem(item.barcode)}
                      className="w-6 h-6 rounded text-gray-300 hover:text-red-400 hover:bg-red-50 flex items-center justify-center ms-0.5 transition-colors">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="px-4 py-3 border-t border-gray-200">
              <Button onClick={handleCompare} disabled={comparing} className="w-full" size="lg">
                {comparing ? (
                  <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />{tCommon("loading")}</>
                ) : t("compareAll")}
              </Button>
            </div>
          </motion.div>
        ) : (
          <p className="text-center py-6 text-gray-400 text-sm">{t("empty")}</p>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {results && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}>
            <BasketResults results={results} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
