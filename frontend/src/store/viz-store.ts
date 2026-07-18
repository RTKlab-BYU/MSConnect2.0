import { create } from "zustand";

export type RetentionTimeWindow = {
  startMinutes: number;
  endMinutes: number;
};

type VizState = {
  retentionTimeWindow: RetentionTimeWindow | null;
  selectedCellIds: string[];
  setRetentionTimeWindow: (window: RetentionTimeWindow | null) => void;
  setSelectedCellIds: (cellIds: string[]) => void;
};

export const useVizStore = create<VizState>((set) => ({
  retentionTimeWindow: null,
  selectedCellIds: [],
  setRetentionTimeWindow: (retentionTimeWindow) => set({ retentionTimeWindow }),
  setSelectedCellIds: (selectedCellIds) => set({ selectedCellIds }),
}));
