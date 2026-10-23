export function bankIdentifiers(account: string | undefined, upis: string[] = []): string {
  return [...new Map([account, ...upis].filter((value): value is string => Boolean(value?.trim())).map((value) => [value.trim().toLowerCase(), value.trim()])).values()].join(" · ");
}
