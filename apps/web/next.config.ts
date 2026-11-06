import type { NextConfig } from "next";
const config: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.LAB_API_URL || "http://127.0.0.1:8100"}/api/v1/:path*`,
      },
    ];
  },
};
export default config;
