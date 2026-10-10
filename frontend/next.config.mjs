/** @type {import('next').NextConfig} */
const nextConfig = {
  // Build independiente de node_modules para el contenedor de despliegue
  // (Dockerfile raíz: Next standalone + uvicorn, un solo origen).
  output: "standalone",
  // El frontend habla SIEMPRE con el mismo origen (mismo-origen cookies):
  // /api/* se reescribe al backend (http://127.0.0.1:8000/api/v1/*). En
  // producción el proxy puede hacer esto con Nginx/Caddy, o se apunta
  // BACKEND_URL al host del backend.
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
      // Cron del sistema: el job interno entra por el mismo origen.
      {
        source: "/internal/:path*",
        destination: `${backend}/internal/:path*`,
      },
      // OpenAPI/Swagger del backend proxeado (extra de la guía).
      {
        source: "/openapi.json",
        destination: `${backend}/openapi.json`,
      },
      {
        source: "/docs",
        destination: `${backend}/docs`,
      },
    ];
  },
};

export default nextConfig;