import Link from "next/link";
import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <header className="page-header">
    <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{description && <p className="intro">{description}</p>}</div>
    {action && <div className="page-header-actions">{action}</div>}
  </header>;
}

export function MetricCard({ label, value, note, tone = "default", href }: { label: string; value: ReactNode; note?: ReactNode; tone?: "default" | "positive" | "warning" | "danger" | "accent"; href?: string }) {
  const content = <><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong>{note && <small>{note}</small>}</>;
  return href ? <Link className={`metric-card tone-${tone}`} href={href}>{content}</Link> : <div className={`metric-card tone-${tone}`}>{content}</div>;
}

export function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "positive" | "warning" | "danger" | "info" }) {
  return <span className={`status-badge tone-${tone}`}>{children}</span>;
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-state-mark" aria-hidden="true">—</span><div><strong>{title}</strong>{detail && <p>{detail}</p>}</div>{action && <div className="empty-state-action">{action}</div>}</div>;
}

export function SectionHeading({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action && <div>{action}</div>}</div>;
}

export function Skeleton({ lines = 4 }: { lines?: number }) {
  return <div className="skeleton-stack" aria-label="Loading" role="status">{Array.from({ length: lines }, (_, index) => <span key={index} className="skeleton-line" />)}</div>;
}
