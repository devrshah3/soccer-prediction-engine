import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next 16 blocks the dev HMR WebSocket from any origin except `localhost`, so opening the
  // dev server at http://127.0.0.1:3000 logs a failed /_next/hmr handshake that the dev
  // overlay counts as "1 Issue". Dev-only; has no effect on production builds.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
