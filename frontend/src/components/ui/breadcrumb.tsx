import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

export type BreadcrumbItem = {
  label: string;
  href?: string;
};

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-muted-foreground">
      {items.map((item, index) => (
        <div className="flex items-center gap-1" key={`${item.label}-${index}`}>
          {index > 0 ? <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" /> : null}
          {item.href ? (
            <Link className="font-semibold text-muted-foreground hover:text-foreground" to={item.href}>
              {item.label}
            </Link>
          ) : (
            <span className="font-semibold text-foreground">{item.label}</span>
          )}
        </div>
      ))}
    </nav>
  );
}
