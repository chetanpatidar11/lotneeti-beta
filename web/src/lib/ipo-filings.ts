export type SEBIFiling = {
  issuer_name: string;
  document_type: string;
  document_url: string;
  filing_date: string;
};

function issuerKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "").replace(/limited$/, "");
}

export function filingsForIssuer(issuerName: string, filings: SEBIFiling[]): SEBIFiling[] {
  const key = issuerKey(issuerName);
  return key ? filings.filter((filing) => issuerKey(filing.issuer_name) === key) : [];
}