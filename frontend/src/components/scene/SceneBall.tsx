"use client";

import { useEffect, useRef, useState } from "react";
import type { BallHandle } from "./ballScene";

const WIDE = "(min-width: 900px)";
const REDUCED = "(prefers-reduced-motion: reduce)";

// The realistic 3D ball behind everything. Guard rails (all mandatory): the three.js chunk is
// only ever loaded via dynamic import, and only when the viewport is >= 900px wide, reduced
// motion is off and Save-Data is off. Otherwise - and if WebGL fails - the pre-rendered
// static image of the SAME ball (public/scene/ball.webp) stays put, same position and blur.
// The loop is capped at 30fps and DPR 1.5, pauses when the tab is hidden or the ball scrolls
// out of view, and everything is disposed on unmount.
function use3DAllowed(): boolean {
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    const wide = window.matchMedia(WIDE);
    const reduced = window.matchMedia(REDUCED);
    const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
    const update = () => setAllowed(wide.matches && !reduced.matches && !saveData);
    update();
    wide.addEventListener("change", update);
    reduced.addEventListener("change", update);
    return () => {
      wide.removeEventListener("change", update);
      reduced.removeEventListener("change", update);
    };
  }, []);
  return allowed;
}

export function SceneBall() {
  const allowed = use3DAllowed();
  const wrapper = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (!allowed) return;
    const wrapperEl = wrapper.current;
    let cancelled = false;
    let handle: BallHandle | null = null;
    let canvas: HTMLCanvasElement | null = null;
    let observer: IntersectionObserver | null = null;
    let resizer: ResizeObserver | null = null;
    let onVisibility: (() => void) | null = null;
    let onScroll: (() => void) | null = null;
    let scrollRaf = 0;
    let settle = 0;

    import("./ballScene")
      .then(({ createBall }) => {
        const el = wrapper.current;
        const mount = host.current;
        if (cancelled || !el || !mount) return;
        canvas = document.createElement("canvas");
        canvas.className = "absolute inset-0 h-full w-full";
        mount.appendChild(canvas);
        try {
          handle = createBall(canvas);
        } catch {
          canvas.remove();
          canvas = null;
          return; // WebGL unavailable: the static image stays
        }
        const size = () => handle?.resize(el.clientWidth, el.clientHeight);
        size();
        resizer = new ResizeObserver(size);
        resizer.observe(el);

        let inView = true;
        let scrolling = false;
        const sync = () => handle?.setActive(inView && !document.hidden && !scrolling);
        observer = new IntersectionObserver(([entry]) => {
          inView = entry.isIntersecting;
          sync();
        });
        observer.observe(el);
        onVisibility = sync;
        document.addEventListener("visibilitychange", onVisibility);

        // Gentle scroll parallax (the ball drifts up slower than the page).
        // The ball also freezes while the page is scrolling and resumes shortly after: on a
        // machine without a GPU, rendering it during scroll dropped scrolling to ~20fps.
        onScroll = () => {
          scrolling = true;
          sync();
          window.clearTimeout(settle);
          settle = window.setTimeout(() => {
            scrolling = false;
            sync();
          }, 160);
          if (scrollRaf) return;
          scrollRaf = requestAnimationFrame(() => {
            scrollRaf = 0;
            el.style.transform = `translate3d(0, ${(-window.scrollY * 0.12).toFixed(1)}px, 0)`;
          });
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        setLive(true);
      })
      .catch(() => {
        /* chunk failed to load: keep the static image */
      });

    return () => {
      cancelled = true;
      setLive(false);
      if (onVisibility) document.removeEventListener("visibilitychange", onVisibility);
      if (onScroll) window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(scrollRaf);
      window.clearTimeout(settle);
      observer?.disconnect();
      resizer?.disconnect();
      handle?.dispose();
      canvas?.remove();
      if (wrapperEl) wrapperEl.style.transform = "";
    };
  }, [allowed]);

  return (
    <div
      ref={wrapper}
      className="absolute -right-[24vw] -top-[19vw] aspect-square w-[min(52vw,760px)] will-change-transform"
      style={{ filter: "blur(1.5px)", opacity: 0.82 }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- fixed decorative asset, needs no optimizer */}
      <img
        src="/scene/ball.webp"
        alt=""
        decoding="async"
        fetchPriority="low"
        className="absolute inset-0 h-full w-full object-contain"
        style={{ opacity: live ? 0 : 1 }}
      />
      <div ref={host} className="absolute inset-0" style={{ opacity: live ? 1 : 0 }} />
    </div>
  );
}
