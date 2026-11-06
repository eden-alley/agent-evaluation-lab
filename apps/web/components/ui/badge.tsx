import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
const badgeVariants = cva("badge", {
  variants: {
    variant: {
      default: "",
      good: "good",
      warn: "warn",
      bad: "bad",
      info: "info",
    },
  },
  defaultVariants: { variant: "default" },
});
export function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
