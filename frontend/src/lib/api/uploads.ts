import { apiFetch } from "@/lib/api/client";
import type { DirectUploadSession, RawFile } from "@/lib/api/types";

export type CreateDirectUploadInput = {
  project: number;
  run?: number | null;
  filename: string;
  size_bytes: number;
  content_type?: string;
  chunk_size_bytes: number;
  file_role?: RawFile["file_role"];
};

export function createDirectUploadSession(input: CreateDirectUploadInput) {
  return apiFetch<DirectUploadSession>("/direct-uploads/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function completeDirectUploadSession(id: number, checksum_sha256: string) {
  return apiFetch<DirectUploadSession>(`/direct-uploads/${id}/complete/`, {
    method: "POST",
    body: JSON.stringify({ checksum_sha256 }),
  });
}
