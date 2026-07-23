import { AlertTriangle, FileUp, RotateCcw, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { completeDirectUploadSession, createDirectUploadSession } from "@/lib/api/uploads";
import { formatBytes, formatDate } from "@/lib/format";
import { useUploadStore, type UploadFileRecord } from "@/store/upload-store";

function uploadStatusToBadge(status: UploadFileRecord["state"]) {
  if (status === "complete") return "succeeded";
  if (status === "uploading" || status === "preparing") return "running";
  if (status === "failed" || status === "blocked") return "failed";
  if (status === "ready") return "ready";
  return "queued";
}

function progress(file: UploadFileRecord) {
  if (!file.size) return 0;
  return Math.round(((file.uploadedBytes || file.preparedBytes) / file.size) * 100);
}

async function sha256(file: File) {
  const buffer = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export default function UploadsPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const fileObjectsRef = useRef(new Map<string, File>());
  const [projectId, setProjectId] = useState("");
  const files = useUploadStore((state) => state.files);
  const stageFiles = useUploadStore((state) => state.stageFiles);
  const prepareFile = useUploadStore((state) => state.prepareFile);
  const attachDirectUploadSession = useUploadStore((state) => state.attachDirectUploadSession);
  const markUploading = useUploadStore((state) => state.markUploading);
  const updateChunk = useUploadStore((state) => state.updateChunk);
  const markComplete = useUploadStore((state) => state.markComplete);
  const markFailed = useUploadStore((state) => state.markFailed);
  const markBackendBlocked = useUploadStore((state) => state.markBackendBlocked);
  const retry = useUploadStore((state) => state.retry);
  const remove = useUploadStore((state) => state.remove);

  async function startUpload(file: UploadFileRecord) {
    const project = Number(projectId);
    const fileObject = fileObjectsRef.current.get(file.id);
    if (!project) {
      markFailed(file.id, "Enter a project ID before requesting signed upload URLs.");
      return;
    }
    if (!fileObject) {
      markFailed(file.id, "The file object is no longer available in this browser session. Select it again to upload.");
      return;
    }

    try {
      const session = await createDirectUploadSession({
        project,
        filename: file.name,
        size_bytes: file.size,
        content_type: file.type || "application/octet-stream",
        chunk_size_bytes: file.chunkSize,
      });
      attachDirectUploadSession(file.id, session.id, session.storage_key);
      markUploading(file.id);

      for (const part of session.upload_urls) {
        const chunk = fileObject.slice(part.start, part.end);
        updateChunk(file.id, part.part_number - 1, "uploading");
        const response = await fetch(part.url, {
          method: part.method,
          headers: part.headers,
          body: chunk,
        });
        if (!response.ok) {
          throw new Error(`Object storage rejected part ${part.part_number} with status ${response.status}`);
        }
        updateChunk(file.id, part.part_number - 1, "complete", part.end - part.start);
      }

      const checksum = await sha256(fileObject);
      await completeDirectUploadSession(session.id, checksum);
      markComplete(file.id);
    } catch (error) {
      markFailed(file.id, error instanceof Error ? error.message : "Upload failed");
    }
  }

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Uploads" }]} />

      <PageHero
        eyebrow="Distributed ingest"
        title="Uploads"
        description="Stage raw files, prepare chunk manifests, and track upload state without crowding the workspace."
      />

      <Card>
        <CardHeader>
          <CardTitle>Stage raw files</CardTitle>
          <CardDescription>
            Select files, attach them to a project, and prepare resumable upload manifests.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => {
              if (event.target.files) {
                const staged = stageFiles(event.target.files);
                Array.from(event.target.files).forEach((file, index) => {
                  const record = staged[index];
                  if (record) fileObjectsRef.current.set(record.id, file);
                });
              }
              event.currentTarget.value = "";
            }}
          />
          <div className="grid gap-3 md:grid-cols-[240px_auto]">
            <Input
              inputMode="numeric"
              placeholder="Project ID"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            />
            <Button onClick={() => inputRef.current?.click()}>
              <FileUp className="h-4 w-4" />
              Select files
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3">
        {files.map((file) => (
          <Card key={file.id}>
            <CardContent className="grid gap-3 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{file.name}</div>
                  <div className="text-sm text-muted-foreground">
                    {formatBytes(file.size)} · {file.chunks.length} chunks · staged {formatDate(file.createdAt)}
                  </div>
                </div>
                <StatusBadge status={uploadStatusToBadge(file.state)} />
              </div>

              <div className="h-2 overflow-hidden rounded-full bg-secondary">
                <div className="h-full bg-primary" style={{ width: `${progress(file)}%` }} />
              </div>

              {file.error ? (
                <div className="flex items-center gap-2 rounded-2xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  <AlertTriangle className="h-4 w-4" />
                  {file.error}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => prepareFile(file.id)} disabled={file.state === "ready"}>
                  Prepare manifest
                </Button>
                <Button onClick={() => startUpload(file)} disabled={file.state !== "ready"}>
                  Start upload
                </Button>
                <Button variant="secondary" onClick={() => markBackendBlocked(file.id)} disabled={file.state !== "ready"}>
                  Mark adapter missing
                </Button>
                <Button variant="secondary" onClick={() => retry(file.id)} disabled={!["failed", "blocked"].includes(file.state)}>
                  <RotateCcw className="h-4 w-4" />
                  Retry
                </Button>
                <Button variant="ghost" onClick={() => remove(file.id)}>
                  <Trash2 className="h-4 w-4" />
                  Remove
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}

        {!files.length && (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">No files staged.</CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
