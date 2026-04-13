import type { NextConfig } from "next";

function resolveBackendInternalUrl(): string {
  const raw = process.env.BACKEND_INTERNAL_URL?.trim();
  const fallback = "http://agente-ia_backend:8000";

  if (!raw) return fallback;

  const normalized = raw.replace(/\/+$/, "");
  if (
    normalized.startsWith("http://")
    || normalized.startsWith("https://")
    || normalized.startsWith("/")
  ) {
    return normalized;
  }

  return fallback;
}

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const backendInternalUrl = resolveBackendInternalUrl();

    return [
      {
        source: "/api/:path*",
        destination: `${backendInternalUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
