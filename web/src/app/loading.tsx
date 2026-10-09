import { Skeleton, PageHeader } from "@/components/ui";

export default function Loading() {
  return <main className="page"><div className="shell" aria-busy="true" aria-label="Loading page">
    <PageHeader eyebrow="LotNeeti" title="Loading workspace" />
    <Skeleton lines={4} />
  </div></main>;
}
