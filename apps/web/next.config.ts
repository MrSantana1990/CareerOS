import type { NextConfig } from "next";
const config: NextConfig = {
  output: process.env.BUILD_STANDALONE === "true" ? "standalone" : undefined,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/agent/:path*", destination: "http://127.0.0.1:8765/:path*" }];
  },
};
export default config;
