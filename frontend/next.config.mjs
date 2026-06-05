/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy /api/* to the backend so the browser only ever talks to the frontend
  // origin. This keeps the session cookie same-origin (no cross-site cookie /
  // CORS issues). BACKEND_URL is the backend's base URL (e.g. the Railway
  // public URL); defaults to local dev.
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/:path*`,
      },
    ];
  },
};
export default nextConfig;
