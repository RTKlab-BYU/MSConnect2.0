import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { statusDefinition } from "@/lib/status/status-map";

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const definition = statusDefinition(status);
  const Icon = definition.icon;

  return (
    <Badge variant={definition.tone === "error" ? "error" : definition.tone} className={className}>
      <Icon className={cn("h-3.5 w-3.5", status === "running" && "animate-spin")} aria-hidden="true" />
      <span>{definition.label}</span>
    </Badge>
  );
}
