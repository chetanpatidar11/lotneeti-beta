import SignInForm from "./sign-in-form";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { localPreviewEnabled } from "@/lib/local-preview";

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const theme = (await cookies()).get("lotneeti_theme")?.value === "dark" ? "dark" : "light";
  if (localPreviewEnabled()) {
    if (error !== "local") redirect("/auth/local-preview");
    return <main className="page"><div className="shell"><p className="eyebrow">LotNeeti</p><h1>Local preview unavailable</h1><p className="intro">Check that the local API is running, then try again.</p><a className="button-link" href="/auth/local-preview">Retry preview</a></div></main>;
  }
  return <SignInForm linkError={error === "link"} initialTheme={theme} />;
}
