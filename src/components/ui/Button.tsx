import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "solid" | "gradient";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: ButtonVariant;
}

// Flat Minimal: a single, confident violet action. The former "gradient"
// variant is kept in the type so existing call sites compile, but it now maps
// to the same flat accent — the redesign has no gradients.
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  solid: "bg-accent text-white hover:bg-accent-soft disabled:hover:bg-accent",
  gradient: "bg-accent text-white hover:bg-accent-soft disabled:hover:bg-accent",
};

/** Primary action button — solid violet accent (Flat Minimal). */
export function Button({
  children,
  variant = "solid",
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`rounded-xl transition flex items-center justify-center gap-2 font-medium ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
