import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Activity, BarChart3, CheckCircle2, FlaskConical, HardDrive, Search, Settings, UploadCloud } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { fetchProjects, queryKeys } from "@/lib/api/queries";
import { useUiStore } from "@/store/ui-store";

export function CommandPalette() {
  const navigate = useNavigate();
  const open = useUiStore((state) => state.commandOpen);
  const setOpen = useUiStore((state) => state.setCommandOpen);
  const { data } = useQuery({
    queryKey: queryKeys.projects({ page_size: 20 }),
    queryFn: () => fetchProjects({ page_size: 20 }),
  });

  function go(path: string) {
    setOpen(false);
    navigate(path);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="p-0">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <Command className="overflow-hidden rounded-lg">
          <div className="flex items-center border-b px-3">
            <Search className="mr-2 h-4 w-4 text-muted-foreground" />
            <Command.Input
              className="h-11 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              placeholder="Search projects, raw files, jobs, settings..."
            />
          </div>
          <Command.List className="max-h-[420px] overflow-y-auto p-2">
            <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">No results found.</Command.Empty>
            <Command.Group heading="Navigation" className="text-xs text-muted-foreground">
              <Command.Item className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm" onSelect={() => go("/projects")}>
                <FlaskConical className="h-4 w-4" />
                Projects
              </Command.Item>
              <Command.Item className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm" onSelect={() => go("/qc")}>
                <CheckCircle2 className="h-4 w-4" />
                QC
              </Command.Item>
              <Command.Item className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm" onSelect={() => go("/settings")}>
                <Settings className="h-4 w-4" />
                Settings
              </Command.Item>
              <Command.Item className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm" onSelect={() => go("/monitoring")}>
                <Activity className="h-4 w-4" />
                Monitoring
              </Command.Item>
              <Command.Item className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm" onSelect={() => go("/processing")}>
                <HardDrive className="h-4 w-4" />
                Processing
              </Command.Item>
              <Command.Item className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm" onSelect={() => go("/spectra")}>
                <BarChart3 className="h-4 w-4" />
                Spectra
              </Command.Item>
              <Command.Item className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm" onSelect={() => go("/uploads")}>
                <UploadCloud className="h-4 w-4" />
                Uploads
              </Command.Item>
            </Command.Group>
            <Command.Group heading="Projects" className="text-xs text-muted-foreground">
              {(data?.results ?? []).map((project) => (
                <Command.Item
                  key={project.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm"
                  onSelect={() => go(`/projects/${project.id}`)}
                >
                  <HardDrive className="h-4 w-4" />
                  <span className="font-semibold">{project.code}</span>
                  <span className="text-muted-foreground">{project.title}</span>
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
