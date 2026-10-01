import type { NextConfig } from "next";

const api = process.env.HERICR_API_URL || "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  async rewrites() {
    // Brskalnik govori samo z istim izvorom (/api) -> brez CORS, piškotkov ali izpostavljenega backenda.
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default config;
