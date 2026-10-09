export type ApiHealth =
  | { connected: true; message: string }
  | { connected: false; message: string };

type FetchLike = typeof fetch;

export async function getApiHealth(
  apiBaseUrl: string,
  fetchImpl: FetchLike = fetch,
): Promise<ApiHealth> {
  const url = `${apiBaseUrl.replace(/\/+$/, "")}/health/`;

  try {
    const response = await fetchImpl(url, { cache: "no-store" });
    if (!response.ok) {
      return { connected: false, message: "API is unavailable" };
    }

    const payload: unknown = await response.json();
    if (
      typeof payload === "object" &&
      payload !== null &&
      "status" in payload &&
      payload.status === "ok" &&
      "apiVersion" in payload &&
      payload.apiVersion === "v1"
    ) {
      return { connected: true, message: "API connected" };
    }
  } catch {
    // A clear offline state lets the frontend start before the API is running.
  }

  return { connected: false, message: "API is unavailable" };
}
