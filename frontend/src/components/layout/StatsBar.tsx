"use client";

import { useTranslations } from "next-intl";

const stats = [
  { key: "products", value: "143,000+" },
  { key: "chains",   value: "29" },
  { key: "stores",   value: "1,500+" },
  { key: "updatedEvery", value: null },
];

export default function StatsBar() {
  const t = useTranslations("stats");

  return (
    <div className="border-b border-gray-200">
      <div className="max-w-6xl mx-auto px-5 py-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {stats.map((s) => (
            <div key={s.key}>
              {s.value && (
                <span className="font-mono text-xl text-gray-900 tracking-tight">{s.value}</span>
              )}
              <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mt-0.5">
                {t(s.key as keyof typeof t)}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
