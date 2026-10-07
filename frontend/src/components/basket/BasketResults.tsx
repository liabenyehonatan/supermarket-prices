"use client";

import { useTranslations, useLocale } from "next-intl";
import { useEffect, useState } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { BasketCompareResponse } from "@/lib/api";

function CountUp({ to, prefix = "" }: { to: number; prefix?: string }) {
  const raw = useMotionValue(0);
  const spring = useSpring(raw, { stiffness: 45, damping: 12 });
  const [display, setDisplay] = useState("0.00");
  useEffect(() => { raw.set(to); }, [to, raw]);
  useEffect(() => spring.on("change", (v) => setDisplay(v.toFixed(2))), [spring]);
  return <>{prefix}{display}</>;
}

export default function BasketResults({ results }: { results: BasketCompareResponse }) {
  const t = useTranslations("basket");
  const tC = useTranslations("common");
  const locale = useLocale();
  const isRtl = locale === "he";
  const best = results.stores[0];
  const savings = Number(results.max_savings);

  return (
    <div className="space-y-3 mt-3">

      {savings > 0.01 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="border border-brand-200 bg-brand-50 rounded-xl px-4 py-2.5 flex items-center gap-3">
          <div className="w-5 h-5 rounded-full border border-brand-200 bg-brand-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-3 h-3 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
          </div>
          <span className="text-sm text-brand-700">
            {isRtl ? `חיסכון אפשרי של ${tC("nis")}${savings.toFixed(2)}` : `Save up to ${tC("nis")}${savings.toFixed(2)}`}
          </span>
        </motion.div>
      )}

      {best && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
          className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2 mb-0.5">
                  <span className="text-[10px] font-semibold tracking-widest uppercase text-gray-300">01</span>
                  <span className="text-[10px] font-semibold tracking-wide uppercase text-brand-600 bg-brand-50 border border-brand-100 px-2 py-0.5 rounded">{t("cheapestStore")}</span>
                </div>
                <p className={`text-xl text-gray-900 leading-tight truncate ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
                  {best.store.chain.name}
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  {[best.store.name, best.store.city].filter(Boolean).join(" · ")}
                  {best.items_missing > 0 && <span className="text-amber-500"> · {best.items_missing} {t("missing")}</span>}
                </p>
              </div>
              <div className="text-end flex-shrink-0">
                <p className="font-mono text-3xl text-gray-900 tabular-nums leading-none">
                  <CountUp to={Number(best.total_price)} prefix={tC("nis")} />
                </p>
              </div>
            </div>
          </div>
          <div className="px-4 pb-4">
            <button
              onClick={() => alert(`Transfer basket to ${best.store.chain.name}`)}
              className="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold transition-colors"
            >
              {t("transferBasket")} — {best.store.chain.name}
            </button>
          </div>
        </motion.div>
      )}

      {results.stores.slice(1, 3).length > 0 && (
        <div className={`grid gap-2 ${results.stores[2] ? "grid-cols-2" : "grid-cols-1"}`}>
          {results.stores.slice(1, 3).map((s, i) => {
            const d = Number(s.total_price) - Number(best.total_price);
            return (
              <motion.div key={s.store.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08 + i * 0.06 }}
                className="border border-gray-200 rounded-xl p-3 hover:border-gray-300 transition-colors">
                <span className="text-[10px] font-semibold tracking-widest text-gray-300 uppercase block mb-0.5">
                  {String(i + 2).padStart(2, "0")}
                </span>
                <p className={`text-base text-gray-900 leading-tight truncate ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
                  {s.store.chain.name}
                </p>
                {s.store.city && <p className="text-[10px] text-gray-400 mt-0.5 truncate">{s.store.city}</p>}
                <p className="font-mono text-lg text-gray-700 mt-1.5 tabular-nums">{tC("nis")}{Number(s.total_price).toFixed(2)}</p>
                {d > 0.01 && <p className="text-[10px] text-amber-500">+{tC("nis")}{d.toFixed(2)}</p>}
              </motion.div>
            );
          })}
        </div>
      )}

      {results.stores.slice(3).length > 0 && (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="divide-y divide-gray-100">
            {results.stores.slice(3).map((s, i) => {
              const d = Number(s.total_price) - Number(best.total_price);
              return (
                <div key={s.store.id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="text-[10px] font-semibold text-gray-300 w-6 flex-shrink-0">{String(i + 4).padStart(2, "0")}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 truncate">{s.store.chain.name}</p>
                    {s.store.city && <p className="text-[10px] text-gray-400">{s.store.city}</p>}
                  </div>
                  <div className="text-end flex-shrink-0">
                    <p className="font-mono text-sm text-gray-700 tabular-nums">{tC("nis")}{Number(s.total_price).toFixed(2)}</p>
                    {d > 0.01 && <p className="text-[10px] text-amber-500">+{tC("nis")}{d.toFixed(2)}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
