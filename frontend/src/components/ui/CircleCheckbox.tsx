"use client";

import type { ComponentPropsWithoutRef } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

type CircleCheckboxProps = Omit<ComponentPropsWithoutRef<"input">, "type"> & {
  indicatorClassName?: string;
};

export default function CircleCheckbox({
  className,
  indicatorClassName,
  disabled,
  ...props
}: CircleCheckboxProps) {
  return (
    <label
      className={cn(
        "relative inline-flex h-5 w-5 shrink-0 items-center justify-center",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
        className
      )}
    >
      <input
        type="checkbox"
        disabled={disabled}
        className="peer sr-only"
        {...props}
      />
      <span
        aria-hidden="true"
        className={cn(
          "flex h-5 w-5 items-center justify-center rounded-full border border-slate-300 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.06)] transition-all duration-200",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-cyan-500/55 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-white",
          "peer-checked:border-[rgb(var(--zy-brand-blue))] peer-checked:bg-[rgb(var(--zy-brand-blue))]",
          "peer-disabled:border-slate-200 peer-disabled:bg-slate-100",
          "dark:border-slate-600 dark:bg-slate-900/70 dark:peer-checked:border-[rgba(var(--zy-brand-blue),0.9)] dark:peer-checked:bg-[rgba(var(--zy-brand-blue),0.9)] dark:peer-disabled:border-slate-700 dark:peer-disabled:bg-slate-800",
          indicatorClassName
        )}
      >
        <Check className="h-3 w-3 text-white opacity-0 transition-opacity duration-150 peer-checked:opacity-100" />
      </span>
    </label>
  );
}
