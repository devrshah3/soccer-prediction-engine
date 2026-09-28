"use client";

import { useEffect, useRef } from "react";
import { createBall } from "@/components/scene/ballScene";

const SIZE = 1000;

declare global {
  interface Window {
    __ballCapture?: (rotationY: number, quality: number) => string;
  }
}

export function BallCapture() {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // A fresh canvas per effect run: a disposed renderer force-loses its context for good.
    const canvas = document.createElement("canvas");
    canvas.style.cssText = `width:${SIZE}px;height:${SIZE}px`;
    host.current?.appendChild(canvas);
    const ball = createBall(canvas, { preserveDrawingBuffer: true });
    ball.setActive(false);
    ball.resize(SIZE, SIZE);
    window.__ballCapture = (rotationY, quality) => {
      ball.renderAt(rotationY);
      return canvas.toDataURL("image/webp", quality);
    };
    return () => {
      delete window.__ballCapture;
      ball.dispose();
      canvas.remove();
    };
  }, []);
  return <div ref={host} />;
}
