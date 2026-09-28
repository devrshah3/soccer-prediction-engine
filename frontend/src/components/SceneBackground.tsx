// Fixed, non-interactive decorative layer behind every page: a stylized blue soccer ball
// (top-right, rotated, soft glow), faint pitch lines, and two blurred accent orbs. Pure
// SVG/CSS, no images/logos. `aria-hidden` + pointer-events:none since it's purely
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

      {/* Stylized soccer ball, top-right, rotated ~-14deg, ~60% opacity, soft blue glow */}
      <svg
        className="scene-drift absolute -right-10 -top-10 h-40 w-40 sm:-right-16 sm:-top-16 sm:h-64 sm:w-64 md:h-80 md:w-80"
        style={{
          transform: "rotate(-14deg)",
          opacity: 0.6,
          filter: "drop-shadow(0 0 46px var(--accent-glow))",
          animation: "scene-drift-c 70s ease-in-out infinite",
        }}
        viewBox="0 0 200 200"
        fill="none"
      >
        <circle cx="100" cy="100" r="92" fill="url(#ballGradient)" stroke="var(--accent-2)" strokeWidth="1.5" />
        <g stroke="var(--accent-2)" strokeWidth="1.4" strokeLinejoin="round" fill="rgba(125,178,255,0.14)">
          <polygon points="100,58 118,71 111,92 89,92 82,71" />
          <polygon points="100,58 118,71 138,64 140,42 118,38" />
          <polygon points="82,71 60,64 58,42 80,38 100,58" />
          <polygon points="111,92 132,108 122,130 100,130 89,92" />
          <polygon points="89,92 68,108 78,130 100,130 111,92" />
          <polygon points="60,64 40,78 44,104 68,108 82,71" />
          <polygon points="138,64 158,78 154,104 132,108 111,92" />
        </g>
        <defs>
          <radialGradient id="ballGradient" cx="35%" cy="30%" r="75%">
            <stop offset="0%" stopColor="#183a7a" />
            <stop offset="100%" stopColor="#081433" />
          </radialGradient>
        </defs>
      </svg>

      <style>{`
        @keyframes scene-drift-a { 0%,100% { transform: translate(0,0); } 50% { transform: translate(24px,-18px); } }
        @keyframes scene-drift-b { 0%,100% { transform: translate(0,0); } 50% { transform: translate(-20px,16px); } }
        @keyframes scene-drift-c { 0%,100% { transform: rotate(-14deg) translateY(0); } 50% { transform: rotate(-11deg) translateY(10px); } }
      `}</style>
    </div>
  );
}
