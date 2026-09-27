"use client";

import Link from "next/link";
import { useState } from "react";
import { MenuIcon, CloseIcon } from "./Icons";

export function MobileNav({ links }: { links: { href: string; label: string }[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sm:hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Toggle navigation menu"
        className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted hover:text-foreground"
      >
        {open ? <CloseIcon className="h-4 w-4" /> : <MenuIcon className="h-4 w-4" />}
      </button>
      {open && (
        <div className="fixed inset-x-0 top-[57px] z-40 border-b border-border bg-surface px-4 py-3 shadow-xl">
          <div className="flex flex-col gap-1">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="rounded-md px-3 py-2 text-sm font-medium text-muted hover:bg-surface-raised hover:text-foreground"
              >
                {l.label}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
