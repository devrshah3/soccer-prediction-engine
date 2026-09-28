"use client";

import { useEffect } from "react";
import { CloseIcon } from "../Icons";

// A glass modal sheet (the "Points table" popup in item 3, reusable anywhere else a
// full-detail overlay is needed). Closes on Escape or backdrop click; traps nothing fancy
// beyond that, kept simple.
export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="glass glass-float relative max-h-[85vh] w-full overflow-y-auto !rounded-b-none !rounded-t-3xl p-5 sm:max-w-2xl sm:!rounded-3xl sm:p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 items-center justify-center rounded-full text-muted transition-colors hover:bg-white/10 hover:text-foreground"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
