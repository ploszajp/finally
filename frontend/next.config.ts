import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Production: static export to `out/`, served by FastAPI on the same origin.
// Development (`next dev`): proxy /api/* to the FastAPI backend. Rewrites are
// not supported by `output: 'export'`, so they exist only in the dev phase.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const turbopack: NextConfig["turbopack"] = {
  rules: {
    "*.css": {
      loaders: ["@tailwindcss/turbopack"],
      as: "*.css",
    },
  },
};

export default function config(phase: string): NextConfig {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      turbopack,
      // Do not gzip proxied responses; compression buffers the SSE stream.
      compress: false,
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
      },
    };
  }
  return {
    output: "export",
    images: { unoptimized: true },
    turbopack,
  };
}
