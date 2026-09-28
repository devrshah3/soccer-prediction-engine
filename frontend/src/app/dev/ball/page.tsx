import { notFound } from "next/navigation";
import { BallCapture } from "./BallCapture";

// Dev-only: renders the 3D ball on a transparent canvas so scripts/render-ball-fallback.mjs can
// export the static WebP used on mobile / reduced motion / no-WebGL. 404s in production.
export default function BallCapturePage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <BallCapture />;
}
