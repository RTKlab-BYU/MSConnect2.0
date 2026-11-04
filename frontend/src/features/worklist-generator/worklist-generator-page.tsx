import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { WorklistGeneratorFlow } from "@/features/worklist-generator/worklist-generator-flow";

export default function WorklistGeneratorPage() {
  return (
    <div className="grid min-w-0 gap-4">
      <Breadcrumbs items={[{ label: "Projects", href: "/projects" }, { label: "Worklist Generator" }]} />
      <PageHero
        eyebrow="Acquisition setup"
        title="Worklist Generator"
        description="Create a metadata workbook, complete the plate layout, then generate the MS and LC sequence files."
        actions={(
          <Button asChild variant="secondary">
            <Link to="/projects"><ArrowLeft aria-hidden="true" className="h-4 w-4" />Projects</Link>
          </Button>
        )}
      />
      <WorklistGeneratorFlow />
    </div>
  );
}
