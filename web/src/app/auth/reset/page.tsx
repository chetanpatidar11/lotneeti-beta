import ResetPassword from "./reset-password";

export default async function ResetPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return <ResetPassword token={token ?? ""} />;
}
