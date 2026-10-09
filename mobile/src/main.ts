import { Browser } from "@capacitor/browser";
import "./style.css";

const betaUrl = import.meta.env.VITE_LOTNEETI_WEB_URL;
const button = document.querySelector<HTMLButtonElement>("#open-app");
const message = document.querySelector<HTMLElement>("#message");

if (!button || !message) throw new Error("Android launch screen is incomplete");

button.addEventListener("click", async () => {
  button.disabled = true;
  message.textContent = "Opening LotNeeti…";
  try {
    await Browser.open({ url: betaUrl, toolbarColor: "#102a38" });
    message.textContent = "";
  } catch {
    message.textContent = "Could not open LotNeeti. Check your connection and try again.";
  } finally {
    button.disabled = false;
  }
});
