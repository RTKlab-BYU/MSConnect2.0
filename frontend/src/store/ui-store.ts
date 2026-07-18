import { create } from "zustand";

type Theme = "light" | "dark";

type UiState = {
  theme: Theme;
  commandOpen: boolean;
  setTheme: (theme: Theme) => void;
  setCommandOpen: (open: boolean) => void;
};

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export const useUiStore = create<UiState>((set) => ({
  theme: document.documentElement.classList.contains("dark") ? "dark" : "light",
  commandOpen: false,
  setTheme: (theme) => {
    applyTheme(theme);
    set({ theme });
  },
  setCommandOpen: (commandOpen) => set({ commandOpen }),
}));
