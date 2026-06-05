/** @type {import('next').NextConfig} */

// Normalize BACKEND_URL so the rewrite destination is always valid: Next.js
// requires it to start with "/", "http://" or "https://". If the env var is
// given without a scheme (e.g. "antests-production.up.railway.app"), assume
// https. Strip a trailing slash so we never produce a double slash.
function backendBase() {
  let backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  if (!/^https?:\/\//i.test(backend)) {
    backend = `https://${backend}`;
  }
  return backend.replace(/\/+$/, "");
}

const nextConfig = {
  // Proxy /api/* to the backend so the browser only ever talks to the frontend
  // origin. This keeps the session cookie same-origin (no cross-site cookie /
  // CORS issues).
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendBase()}/:path*`,
      },
    ];
  },
};
export default nextConfig;
