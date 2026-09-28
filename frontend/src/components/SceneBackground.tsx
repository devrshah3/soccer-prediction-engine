import { SceneBall } from "./scene/SceneBall";

// Fixed, non-interactive decorative layer behind every page: a realistic 3D soccer ball
// (top-right, see scene/SceneBall.tsx), faint pitch lines, and two blurred accent orbs. No
// logos or brand marks. `aria-hidden` + pointer-events:none since it's purely
// decorative. The drift animation is disabled under prefers-reduced-motion via the
// .scene-drift rule in globals.css.
export function SceneBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* Blurred accent orbs */}
      <div
        className="scene-drift absolute -left-24 top-1/3 h-72 w-72 rounded-full opacity-40 blur-3xl sm:h-96 sm:w-96"
        style={{ background: "radial-gradient(58% 52% at 97% 0%, transparent 0%, rgba(4,8,26,0.5) 55%, rgba(4,8,26,0.88) 100%)", animation: "scene-drift-a 46s ease-in-out infinite" }}
      />
      <div
        className="scene-drift absolute bottom-0 right-1/4 h-64 w-64 rounded-full opacity-30 blur-3xl sm:h-80 sm:w-80"
        style={{ background: "radial-gradient(circle, var(--accent), transparent 70%)", animation: "scene-drift-b 58s ease-in-out infinite" }}
      />

      {/* Faint pitch lines - center circle, halfway line, box arcs */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 1440 900"
        preserveAspectRatio="xMidYMid slice"
        style={{ opacity: 0.1 }}
      >
        <line x1="720" y1="0" x2="720" y2="900" stroke="white" strokeWidth="2" />
        <circle cx="720" cy="450" r="140" stroke="white" strokeWidth="2" fill="none" />
        <circle cx="720" cy="450" r="4" fill="white" />
        <path d="M 720 250 A 300 300 0 0 1 720 650" stroke="white" strokeWidth="2" fill="none" />
        <path d="M 0 300 L 160 300 A 160 160 0 0 1 160 600 L 0 600" stroke="white" strokeWidth="2" fill="none" />
        <path d="M 1440 300 L 1280 300 A 160 160 0 0 0 1280 600 L 1440 600" stroke="white" strokeWidth="2" fill="none" />
      </svg>

      {/* The realistic 3D ball (static WebP fallback when 3D isn't allowed) + a vignette so the
          cards stay the focus */}
      <SceneBall />
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(90% 75% at 92% 4%, transparent 22%, rgba(4,8,26,0.45) 62%, rgba(4,8,26,0.72) 100%)" }}
      />

      <style>{`
        @keyframes scene-drift-a { 0%,100% { transform: translate(0,0); } 50% { transform: translate(24px,-18px); } }
        @keyframes scene-drift-b { 0%,100% { transform: translate(0,0); } 50% { transform: translate(-20px,16px); } }
      `}</style>
    </div>
  );
}
