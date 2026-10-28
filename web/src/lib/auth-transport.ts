import { isIP } from "node:net";
import { backendUrl, frontendBaseUrl } from "./backend";

// Nginx supplies X-Real-IP and overwrites any browser-supplied value. Only the
// loopback-bound Next server may forward it directly to loopback-bound Django.
export function authTransport(
  path: string,
  clientIp: string | null,
  production = process.env.NODE_ENV === "production",
  frontend = frontendBaseUrl,
): { url: string; headers: Record<string, string> } {
  const origin = new URL(frontend);
  if (production && (!clientIp || !isIP(clientIp))) {
    throw new Error("The trusted proxy client address is missing.");
  }
  return {
    url: production
      ? `http://127.0.0.1:8000/api/v1/${path.replace(/^\/+/, "")}`
      : backendUrl(path),
    headers: {
      "content-type": "application/json",
      origin: origin.origin,
      ...(clientIp && isIP(clientIp) ? { "x-real-ip": clientIp } : {}),
      ...(production ? { host: origin.host, "x-forwarded-proto": origin.protocol.slice(0, -1) } : {}),
    },
  };
}
