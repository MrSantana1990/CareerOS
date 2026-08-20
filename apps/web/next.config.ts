import type { NextConfig } from "next";
const config: NextConfig = {
  output: process.env.BUILD_STANDALONE === "true" ? "standalone" : undefined,
  poweredByHeader: false,
  async rewrites() {
    const automationHost = process.env.AUTOMATION_HOST_URL ?? "http://127.0.0.1:8765";
    const foundationApi = process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001";
    return [
      { source: "/agent/:path*", destination: `${automationHost}/:path*` },
      { source: "/api/v1/:path*", destination: `${foundationApi}/api/v1/:path*` },
      { source: "/health/:path*", destination: `${foundationApi}/health/:path*` },
    ];
  },
};
export default config;
