"use client";

import Link from "next/link";
import { useBasket } from "@/lib/basket-store";

export default function BasketIndicator({ locale }: { locale: string }) {
  const { items } = useBasket();
  const count = items.reduce((sum, i) => sum + i.quantity, 0);

  return (
    <Link href={`/${locale}`}
      className="relative flex items-center justify-center w-9 h-9 rounded-lg hover:bg-gray-50 transition-colors"
      aria-label={`Basket (${count} items)`}>
      <svg className="w-[18px] h-[18px] text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
      {count > 0 && (
        <span className="absolute -top-0.5 -end-0.5 min-w-[16px] h-[16px] px-1 rounded-full bg-brand-600 text-white text-[9px] font-mono flex items-center justify-center">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}
