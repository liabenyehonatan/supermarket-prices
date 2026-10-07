"use client";

import Image from "next/image";
import { useTranslations } from "next-intl";
import { Product } from "@/lib/api";

interface Props {
  product: Product;
  onAdd?: () => void;
  onClick?: () => void;
  compact?: boolean;
}

export default function ProductCard({ product, onAdd, onClick, compact }: Props) {
  const t = useTranslations("product");

  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-3 px-4 cursor-pointer hover:bg-gray-50 border-b border-gray-100 last:border-0 transition-colors ${compact ? "py-2" : "py-2.5"}`}
    >
      <div className="w-9 h-9 rounded-lg bg-gray-100 flex-shrink-0 overflow-hidden flex items-center justify-center">
        {product.image_url ? (
          <Image src={product.image_url} alt={product.name} width={36} height={36}
            className="object-contain w-full h-full"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
        ) : (
          <span className="text-[9px] text-gray-300">N/A</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-900 truncate">{product.name}</p>
        {product.brand && <p className="text-[10px] text-gray-400">{product.brand}</p>}
      </div>
      {onAdd && (
        <button
          onClick={(e) => { e.stopPropagation(); onAdd(); }}
          className="flex-shrink-0 w-7 h-7 rounded-lg bg-brand-600 hover:bg-brand-700 text-white flex items-center justify-center transition-colors"
          title={t("addToBasket")}
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </button>
      )}
    </div>
  );
}
