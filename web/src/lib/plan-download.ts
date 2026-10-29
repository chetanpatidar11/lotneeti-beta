export async function exportError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    return typeof data.detail === "string" ? data.detail : typeof data.message === "string" ? data.message : fallback;
  } catch {
    return fallback;
  }
}

export async function downloadPlanCsv(response: Response): Promise<void> {
  if (!response.ok) throw new Error(await exportError(response, "We could not export this plan."));
  if (!response.headers.get("content-type")?.startsWith("text/csv")) {
    throw new Error("The export did not return a CSV file. Please try again.");
  }
  const blob = await response.blob();
  if (!blob.size) throw new Error("The exported file is empty. Please try again.");
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "lotneeti-plan.csv";
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Keep the blob alive until the browser has begun consuming the download.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
