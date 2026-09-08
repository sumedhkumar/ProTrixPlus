/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  eslint: {
    // Lint is run explicitly in CI via `npm run lint`.
    ignoreDuringBuilds: false,
  },
  env: {
    // Server-only base URL for the api service.
    PROTRIX_API_URL: process.env.PROTRIX_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
