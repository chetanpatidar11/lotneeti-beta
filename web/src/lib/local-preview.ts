export function localPreviewEnabled(
  nodeEnv = process.env.NODE_ENV,
  flag = process.env.LOTNEETI_LOCAL_PREVIEW_AUTH,
): boolean {
  return nodeEnv === "development" && flag === "1";
}
