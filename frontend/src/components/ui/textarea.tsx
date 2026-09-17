import * as React from "react";

import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-9 w-full resize-none rounded-lg border border-transparent bg-transparent px-3 py-2 text-sm text-foreground outline-none",
        "placeholder:text-muted-foreground/80",
        "focus-visible:border-primary/40 focus-visible:ring-0",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
