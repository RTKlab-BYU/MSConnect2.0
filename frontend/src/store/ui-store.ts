import { create } from "zustand";

type UiState = {
  commandOpen: boolean;
  setCommandOpen: (open: boolean) => void;
};

export const useUiStore = create<UiState>((set) => ({
  commandOpen: false,
  setCommandOpen: (commandOpen) => set({ commandOpen }),
}));
