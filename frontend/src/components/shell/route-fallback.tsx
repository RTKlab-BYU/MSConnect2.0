import { Loader2 } from "lucide-react";

export function RouteFallback({ label }: { label: string }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-lg border bg-card text-sm text-muted-foreground">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}
