import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "solid" | "gradient";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: ButtonVariant;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  solid: "bg-violet-600 hover:bg-violet-500",
  gradient:
    "bg-gradient-to-r from-violet-600 to-blue-600 hover:opacity-90",
};

/** Primary action button with violet solid / gradient variants. */
export function Button({
  children,
  variant = "solid",
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`rounded-2xl transition flex items-center justify-center gap-2 font-medium ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
