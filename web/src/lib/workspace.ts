export async function selectedWorkspace<T extends { id: string }>(items: T[]): Promise<T | undefined> {
  // Accounts use their automatically provisioned personal data scope. Ignore
  // legacy selection cookies so every page consistently opens the same account.
  return items[0];
}
