export function validateBetaUrl(value) {
  if (!value) throw new Error("Set VITE_LOTNEETI_WEB_URL to the hosted HTTPS beta site before building Android assets.");
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("VITE_LOTNEETI_WEB_URL must be a valid HTTPS URL.");
  }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("VITE_LOTNEETI_WEB_URL must be an HTTPS site origin with no credentials, path, query or fragment.");
  }
  return url.origin;
}
