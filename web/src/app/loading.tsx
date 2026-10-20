import { Skeleton, PageHeader } from "@/components/ui";

export default function Loading() {
  return <main className="page"><div className="shell" aria-busy="true" aria-label="Loading page">
    <PageHeader eyebrow="LotNeeti" title="Loading workspace" />
    <p className="page-loading-label" role="status"><span className="api-loading-spinner" aria-hidden="true" />Loading page…</p>
    <Skeleton lines={4} />
  </div></main>;
}
