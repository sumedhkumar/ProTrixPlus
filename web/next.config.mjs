/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  eslint: {
    // Lint is run explicitly in CI via `npm run lint`.
    ignoreDuringBuilds: false,
  },
  // PROTRIX_API_URL is deliberately NOT declared under `env:` here. That key
  // inlines a value at *build* time, which bakes whatever the builder happened
  // to see into the bundle - so a container built once and run anywhere would
  // keep calling the build machine's api URL and silently ignore the env var
  // set on the service. It is server-only config (never NEXT_PUBLIC_, and the
  // only client imports of lib/api are `import type`, which TypeScript erases),
  // so the standalone server can just read process.env at runtime instead.
  // Each consumer keeps its own `?? "http://localhost:8000"` fallback for local
  // dev; see web/lib/api.ts and web/lib/proxy.ts.
};

export default nextConfig;
