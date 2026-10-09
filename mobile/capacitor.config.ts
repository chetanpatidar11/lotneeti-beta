import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.lotneeti.beta",
  appName: "LotNeeti Beta",
  webDir: "dist",
  loggingBehavior: "none",
  android: { allowMixedContent: false },
};

export default config;
