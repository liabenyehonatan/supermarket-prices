"use client";

import { useTranslations, useLocale } from "next-intl";

const steps = [
  { number: "01", titleKey: "step1Title", descKey: "step1Desc" },
  { number: "02", titleKey: "step2Title", descKey: "step2Desc" },
  { number: "03", titleKey: "step3Title", descKey: "step3Desc" },
];

export default function HowItWorks() {
  const t = useTranslations("how");
  const isRtl = useLocale() === "he";

  return (
    <section id="how" className="py-20 md:py-28 max-w-6xl mx-auto px-5">
      <h2 className={`text-3xl text-gray-900 text-center mb-14 tracking-tight ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
        {t("title")}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {steps.map((step, i) => (
          <div key={i} className="relative group">
            {i < steps.length - 1 && (
              <div className="hidden md:block absolute top-8 start-full w-full h-px bg-gray-200 -translate-x-1/2 z-0" />
            )}
            <div className="relative bg-gray-50 rounded-xl border border-gray-200 p-8 text-center hover:border-gray-300 transition-colors">
              <span className="text-[11px] font-semibold tracking-widest uppercase text-gray-300 block mb-4">
                {step.number}
              </span>
              <h3 className={`text-lg text-gray-900 mb-2 ${isRtl ? "font-hebrew font-bold" : "font-bold"}`}>
                {t(step.titleKey as keyof typeof t)}
              </h3>
              <p className="text-sm text-gray-500 leading-relaxed">
                {t(step.descKey as keyof typeof t)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
