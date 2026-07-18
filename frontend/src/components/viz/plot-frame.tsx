import type { ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export type PlotFrameProps = {
  title: string;
  description?: string;
  toolbar?: ReactNode;
  children: ReactNode;
};

export function PlotFrame({ title, description, toolbar, children }: PlotFrameProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        {toolbar}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
