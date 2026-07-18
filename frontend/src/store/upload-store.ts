import { persist } from "zustand/middleware";
import { create } from "zustand";

export type UploadChunkState = "pending" | "prepared" | "uploading" | "complete" | "failed";
export type UploadFileState = "staged" | "preparing" | "ready" | "uploading" | "complete" | "failed" | "blocked";

export type UploadChunk = {
  index: number;
  start: number;
  end: number;
  state: UploadChunkState;
  error?: string;
};

export type UploadFileRecord = {
  id: string;
  name: string;
  size: number;
  type: string;
  chunkSize: number;
  state: UploadFileState;
  chunks: UploadChunk[];
  preparedBytes: number;
  uploadedBytes: number;
  directUploadSessionId?: number;
  storageKey?: string;
  error?: string;
  createdAt: string;
  updatedAt: string;
};

type UploadState = {
  files: UploadFileRecord[];
  stageFiles: (files: FileList | File[]) => UploadFileRecord[];
  prepareFile: (id: string) => void;
  attachDirectUploadSession: (id: string, sessionId: number, storageKey: string) => void;
  markUploading: (id: string) => void;
  updateChunk: (id: string, chunkIndex: number, state: UploadChunkState, uploadedBytes?: number) => void;
  markComplete: (id: string) => void;
  markFailed: (id: string, error: string) => void;
  markBackendBlocked: (id: string) => void;
  retry: (id: string) => void;
  remove: (id: string) => void;
};

const CHUNK_SIZE = 8 * 1024 * 1024;

function chunksForFile(file: File): UploadChunk[] {
  const chunks: UploadChunk[] = [];
  for (let start = 0, index = 0; start < file.size; start += CHUNK_SIZE, index += 1) {
    chunks.push({
      index,
      start,
      end: Math.min(start + CHUNK_SIZE, file.size),
      state: "pending",
    });
  }
  return chunks;
}

export const useUploadStore = create<UploadState>()(
  persist(
    (set) => ({
      files: [],
      stageFiles: (incoming) => {
        const now = new Date().toISOString();
        const records = Array.from(incoming).map((file) => ({
          id: crypto.randomUUID(),
          name: file.name,
          size: file.size,
          type: file.type,
          chunkSize: CHUNK_SIZE,
          state: "staged" as const,
          chunks: chunksForFile(file),
          preparedBytes: 0,
          uploadedBytes: 0,
          createdAt: now,
          updatedAt: now,
        }));
        set((state) => ({ files: [...records, ...state.files] }));
        return records;
      },
      prepareFile: (id) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) =>
            file.id === id
              ? {
                  ...file,
                  state: "ready",
                  preparedBytes: file.size,
                  chunks: file.chunks.map((chunk) => ({ ...chunk, state: "prepared" })),
                  updatedAt: now,
                }
              : file,
          ),
        }));
      },
      attachDirectUploadSession: (id, directUploadSessionId, storageKey) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) =>
            file.id === id
              ? {
                  ...file,
                  directUploadSessionId,
                  storageKey,
                  state: "ready",
                  updatedAt: now,
                }
              : file,
          ),
        }));
      },
      markUploading: (id) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) => (file.id === id ? { ...file, state: "uploading", updatedAt: now } : file)),
        }));
      },
      updateChunk: (id, chunkIndex, chunkState, uploadedBytes = 0) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) =>
            file.id === id
              ? {
                  ...file,
                  uploadedBytes: file.uploadedBytes + uploadedBytes,
                  chunks: file.chunks.map((chunk) =>
                    chunk.index === chunkIndex ? { ...chunk, state: chunkState } : chunk,
                  ),
                  updatedAt: now,
                }
              : file,
          ),
        }));
      },
      markComplete: (id) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) =>
            file.id === id
              ? {
                  ...file,
                  state: "complete",
                  uploadedBytes: file.size,
                  chunks: file.chunks.map((chunk) => ({ ...chunk, state: "complete" })),
                  updatedAt: now,
                }
              : file,
          ),
        }));
      },
      markFailed: (id, error) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) =>
            file.id === id ? { ...file, state: "failed", error, updatedAt: now } : file,
          ),
        }));
      },
      markBackendBlocked: (id) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) =>
            file.id === id
              ? {
                  ...file,
                  state: "blocked",
                  error: "Object storage is not configured or reachable for direct browser PUT uploads.",
                  updatedAt: now,
                }
              : file,
          ),
        }));
      },
      retry: (id) => {
        const now = new Date().toISOString();
        set((state) => ({
          files: state.files.map((file) =>
            file.id === id
              ? {
                  ...file,
                  state: "ready",
                  error: undefined,
                  updatedAt: now,
                }
              : file,
          ),
        }));
      },
      remove: (id) => set((state) => ({ files: state.files.filter((file) => file.id !== id) })),
    }),
    {
      name: "msconnect-upload-manifest",
      partialize: (state) => ({ files: state.files }),
    },
  ),
);
