import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Clock3,
  FlaskConical,
  HardDrive,
  HelpCircle,
  Loader2,
  PauseCircle,
  RadioTower,
  XCircle,
} from "lucide-react";

export type StatusTone = "success" | "warning" | "error" | "info" | "neutral";

export type StatusDefinition = {
  label: string;
  tone: StatusTone;
  icon: typeof Circle;
};

export const statusMap: Record<string, StatusDefinition> = {
  active: { label: "Active", tone: "success", icon: CheckCircle2 },
  paused: { label: "Paused", tone: "warning", icon: PauseCircle },
  complete: { label: "Complete", tone: "success", icon: CheckCircle2 },
  archived: { label: "Archived", tone: "neutral", icon: Circle },
  planned: { label: "Planned", tone: "warning", icon: Clock3 },
  acquired: { label: "Acquired", tone: "info", icon: RadioTower },
  imported: { label: "Imported", tone: "success", icon: HardDrive },
  processed: { label: "Processed", tone: "success", icon: CheckCircle2 },
  discovered: { label: "Discovered", tone: "warning", icon: HardDrive },
  validated: { label: "Validated", tone: "info", icon: CheckCircle2 },
  failed: { label: "Failed", tone: "error", icon: XCircle },
  queued: { label: "Queued", tone: "warning", icon: Clock3 },
  assigned: { label: "Assigned", tone: "info", icon: RadioTower },
  running: { label: "Running", tone: "info", icon: Loader2 },
  succeeded: { label: "Succeeded", tone: "success", icon: CheckCircle2 },
  retrying: { label: "Retrying", tone: "warning", icon: Loader2 },
  pass: { label: "Pass", tone: "success", icon: CheckCircle2 },
  warning: { label: "Warning", tone: "warning", icon: AlertCircle },
  incomplete: { label: "Incomplete", tone: "warning", icon: Clock3 },
  draft: { label: "Draft", tone: "warning", icon: Clock3 },
  ready: { label: "Ready", tone: "success", icon: CheckCircle2 },
  acquiring: { label: "Acquiring", tone: "info", icon: RadioTower },
  sample: { label: "Sample", tone: "success", icon: FlaskConical },
  qc: { label: "QC", tone: "info", icon: AlertCircle },
  library: { label: "Library", tone: "neutral", icon: HardDrive },
  blank: { label: "Blank", tone: "neutral", icon: Circle },
  wash: { label: "Wash", tone: "neutral", icon: Circle },
  calibration: { label: "Calibration", tone: "info", icon: AlertCircle },
  offline: { label: "Offline", tone: "error", icon: XCircle },
  idle: { label: "Idle", tone: "success", icon: CheckCircle2 },
  busy: { label: "Busy", tone: "info", icon: Loader2 },
  error: { label: "Error", tone: "error", icon: XCircle },
};

export function statusDefinition(status: string): StatusDefinition {
  return statusMap[status] ?? { label: status || "Unknown", tone: "neutral", icon: HelpCircle };
}
