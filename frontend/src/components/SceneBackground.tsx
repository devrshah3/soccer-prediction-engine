// Fixed, non-interactive decorative layer behind every page: a static line-art soccer ball
// (top-right, public/scene/ball-lines.svg from scripts/make_ball_svg.py), faint pitch lines, and two blurred accent orbs. No
// logos or brand marks. `aria-hidden` + pointer-events:none since it's purely
// decorative. The drift animation is disabled under prefers-reduced-motion via the
// .scene-drift rule in globals.css.
export function SceneBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* Blurred accent orbs */}
      <div
        className="scene-drift absolute -left-24 top-1/3 h-72 w-72 rounded-full opacity-40 blur-3xl sm:h-96 sm:w-96"
        style={{ background: "radial-gradient(circle, var(--accent-2), transparent 70%)", animation: "scene-drift-a 46s ease-in-out infinite" }}
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

      {/* Line-art soccer ball: outlines only (no fills), transparent everywhere. The wrapper carries
          the mask (full strength up in the header area, ~35% opacity down where it sits behind the
          cards) so it stays put while the image inside turns once per 60s (off under reduced motion). */}
      <div
        className="absolute -right-20 -top-16 h-60 w-60 min-[900px]:-right-[140px] min-[900px]:-top-[120px] min-[900px]:h-[520px] min-[900px]:w-[520px]"
        style={{
          maskImage: "linear-gradient(180deg, #000 52%, rgba(0,0,0,0.64) 82%)",
          WebkitMaskImage: "linear-gradient(180deg, #000 52%, rgba(0,0,0,0.64) 82%)",
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- fixed decorative SVG, needs no optimizer */}
        <img
          src="/scene/ball-lines.svg"
          alt=""
          width={520}
          height={520}
          decoding="async"
          className="scene-drift h-full w-full"
          style={{ animation: "scene-ball-turn 60s linear infinite" }}
        />
      </div>
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(90% 75% at 92% 4%, transparent 22%, rgba(4,8,26,0.45) 62%, rgba(4,8,26,0.72) 100%)" }}
      />

      <style>{`
        @keyframes scene-drift-a { 0%,100% { transform: translate(0,0); } 50% { transform: translate(24px,-18px); } }
        @keyframes scene-ball-turn { to { transform: rotate(360deg); } }
        @keyframes scene-drift-b { 0%,100% { transform: translate(0,0); } 50% { transform: translate(-20px,16px); } }
      `}</style>
    </div>
  );
}
