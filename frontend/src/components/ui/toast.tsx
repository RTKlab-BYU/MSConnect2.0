import * as ToastPrimitive from "@radix-ui/react-toast";
import { create } from "zustand";

import { cn } from "@/lib/utils";

type ToastItem = {
  id: string;
  title: string;
  description?: string;
};

type ToastState = {
  items: ToastItem[];
  push: (toast: Omit<ToastItem, "id">) => void;
  dismiss: (id: string) => void;
};

const useToast = create<ToastState>((set) => ({
  items: [],
  push: (toast) =>
    set((state) => ({
      items: [...state.items, { ...toast, id: crypto.randomUUID() }],
    })),
  dismiss: (id) => set((state) => ({ items: state.items.filter((item) => item.id !== id) })),
}));

export function Toaster() {
  const { items, dismiss } = useToast();

  return (
    <ToastPrimitive.Provider swipeDirection="right">
      {items.map((item) => (
        <ToastPrimitive.Root
          key={item.id}
          className={cn("rounded-md border bg-popover p-3 text-popover-foreground shadow-lg")}
          onOpenChange={(open) => {
            if (!open) dismiss(item.id);
          }}
        >
          <ToastPrimitive.Title className="text-sm font-semibold">{item.title}</ToastPrimitive.Title>
          {item.description ? (
            <ToastPrimitive.Description className="mt-1 text-sm text-muted-foreground">
              {item.description}
            </ToastPrimitive.Description>
          ) : null}
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-50 grid w-[360px] max-w-[calc(100vw-2rem)] gap-2" />
    </ToastPrimitive.Provider>
  );
}
