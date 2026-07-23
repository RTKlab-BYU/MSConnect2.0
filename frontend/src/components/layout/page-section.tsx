import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type PageHeroProps = {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  className?: string;
};

export function PageHero({ eyebrow, title, description, actions, className }: PageHeroProps) {
  return (
    <section className={cn("rounded-[2rem] border bg-card/95 p-6 shadow-[0_18px_50px_rgb(15_23_42/0.07)]", className)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.2em] text-accent">{eyebrow}</p>
          <h1 className="mt-2 text-4xl font-black tracking-[-0.055em] text-foreground">{title}</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </section>
  );
}

export function MetricCard({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="text-[11px] font-black uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
        <div className="mt-3 text-3xl font-black tracking-tight">{value}</div>
        <div className="mt-1 text-sm text-muted-foreground">{detail}</div>
      </CardContent>
    </Card>
  );
}
