import type { NextConfig } from "next";

const api = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
const config: NextConfig = {
  devIndicators: false,
  output: "standalone",
  poweredByHeader: false,
  async rewrites() { return [{ source: "/api/:path*", destination: `${api}/:path*` }]; },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      { key: "X-Frame-Options", value: "DENY" }
    ] }, { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }] }];
  }
};
export default config;
