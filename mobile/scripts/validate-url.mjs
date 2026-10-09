import { validateBetaUrl } from "./validate-url-core.mjs";

try {
  validateBetaUrl(process.env.VITE_LOTNEETI_WEB_URL);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
