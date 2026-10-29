import type { NextConfig } from "next";

// Requests to /api/* are forwarded to the FastAPI backend by
// app/api/[...path]/route.ts. (A plain `rewrites()` proxy is not used because
// it gives up after 30 seconds, and local models often need longer.)
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
