"use client";

import { useTranslations, useLocale } from "next-intl";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { compareProduct, ProductCompareResponse } from "@/lib/api";
import { useBasket } from "@/lib/basket-store";
import { Button } from "@/components/ui/button";
import Image from "next/image";

export default function ProductPage() {
  const t = useTranslations("product");
  const tC = useTranslations("common");
  const tF = useTranslations("filters");
  const locale = useLocale();
  const isRtl = locale === "he";
  const params = useParams();
  const barcode = params.barcode as string;
  const { addItem } = useBasket();

  const [data, setData] = useState<ProductCompareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    compareProduct(barcode)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [barcode]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-5 py-20 text-center text-gray-400 text-sm">
        {tC("loading")}
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-3xl mx-auto px-5 py-20 text-center">
        <p className="text-gray-400 text-sm mb-4">{tC("error")}</p>
        <Button variant="secondary" onClick={() => window.location.reload()}>{tC("retry")}</Button>
      </div>
    );
  }

  const { product, prices } = data;
  const cheapest_price = Number(data.cheapest_price);
  const most_expensive_price = Number(data.most_expensive_price);
  const price_difference = Number(data.price_difference);

  return (
    <div className="max-w-3xl mx-auto px-5 py-10">
      {/* Product header */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="flex items-start gap-5 mb-8 pb-8 border-b border-gray-200"
      >
        <div className="w-20 h-20 rounded-xl bg-gray-100 flex-shrink-0 overflow-hidden flex items-center justify-center">
          {product.image_url ? (
            <Image src={product.image_url} alt={product.name} width={80} height={80}
              className="object-contain w-full h-full"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
          ) : (
            <span className="text-xs text-gray-300">{t("noImage")}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h1 className={`text-xl text-gray-900 leading-tight mb-1 ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
            {product.name}
          </h1>
          {product.brand && (
            <p className="text-sm text-gray-400 mb-2">{product.brand}</p>
          )}
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-400">
            <span>{t("barcode")}: {product.barcode}</span>
            {product.unit_of_measure && <span>{product.unit_of_measure}</span>}
          </div>
          <div className="mt-3">
            <Button size="sm" onClick={() => addItem({ barcode: product.barcode, name: product.name, brand: product.brand, imageUrl: product.image_url })}>
              {t("addToBasket")}
            </Button>
          </div>
        </div>
      </motion.div>

      {/* Price summary */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="grid grid-cols-3 gap-3 mb-8"
      >
        <div className="bg-brand-50 border border-brand-100 rounded-xl p-4 text-center">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-brand-600 mb-1">{isRtl ? "הזול" : "Cheapest"}</p>
          <p className="font-mono text-2xl text-gray-900 tabular-nums">{tC("nis")}{cheapest_price.toFixed(2)}</p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-center">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mb-1">{isRtl ? "היקר" : "Most expensive"}</p>
          <p className="font-mono text-2xl text-gray-900 tabular-nums">{tC("nis")}{most_expensive_price.toFixed(2)}</p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-center">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mb-1">{isRtl ? "הפרש" : "Difference"}</p>
          <p className="font-mono text-2xl text-gray-900 tabular-nums">{tC("nis")}{price_difference.toFixed(2)}</p>
        </div>
      </motion.div>

      {/* Price list */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.2 }}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className={`text-lg text-gray-900 ${isRtl ? "font-hebrew font-bold" : "font-bold"}`}>
            {t("price")} {isRtl ? "בסניפים" : "by store"} ({prices.length})
          </h2>
        </div>

        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="divide-y divide-gray-100">
            {prices.map((p, i) => {
              const isCheapest = Number(p.price) === cheapest_price;
              return (
                <div key={`${p.store_id}-${i}`} className={`flex items-center gap-3 px-4 py-3 ${isCheapest ? "bg-brand-50/50" : ""}`}>
                  <span className="text-[10px] font-semibold tracking-widest text-gray-300 w-7 flex-shrink-0">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm text-gray-900 truncate ${isCheapest ? "font-semibold" : ""}`}>
                      {p.chain_name}
                    </p>
                    <p className="text-[10px] text-gray-400 truncate">
                      {[p.store_name, p.store_city].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="text-end flex-shrink-0">
                    <p className={`font-mono text-sm tabular-nums ${isCheapest ? "text-brand-700 font-semibold" : "text-gray-700"}`}>
                      {tC("nis")}{Number(p.price).toFixed(2)}
                    </p>
                    {p.unit_price && (
                      <p className="text-[10px] text-gray-400">{tC("nis")}{Number(p.unit_price).toFixed(2)}/{product.unit_of_measure || (isRtl ? "יח׳" : "unit")}</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
