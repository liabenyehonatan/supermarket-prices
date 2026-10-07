import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { forwardRef } from "react";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 font-bold transition-colors duration-150 cursor-pointer select-none disabled:opacity-40 disabled:cursor-not-allowed rounded-xl",
  {
    variants: {
      variant: {
        primary:   "bg-brand-600 text-white hover:bg-brand-700",
        secondary: "bg-gray-100 text-gray-700 hover:bg-gray-200",
        ghost:     "text-gray-500 hover:text-gray-900 hover:bg-gray-100",
      },
      size: {
        sm: "text-xs px-4 py-2 h-9",
        md: "text-sm px-5 py-2.5 h-10",
        lg: "text-sm px-6 py-3 h-12",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  )
);
Button.displayName = "Button";
export { Button, buttonVariants };
