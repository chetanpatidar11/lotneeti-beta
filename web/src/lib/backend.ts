export const backendApiBaseUrl =
  process.env.API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
export const frontendBaseUrl =
  process.env.FRONTEND_BASE_URL ?? "http://127.0.0.1:3000";

export function backendUrl(path: string): string {
  return `${backendApiBaseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}
