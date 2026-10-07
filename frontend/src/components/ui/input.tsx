import { cn } from "@/lib/utils";
import { forwardRef } from "react";

const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full rounded-xl bg-gray-50 border border-gray-200 px-4 py-3 text-gray-900 text-[15px]",
        "placeholder:text-gray-400",
        "focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100",
        "transition-all duration-150",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
export { Input };
