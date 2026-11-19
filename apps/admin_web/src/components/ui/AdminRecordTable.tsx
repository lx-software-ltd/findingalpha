import type { ReactNode } from "react";

export type AdminFilterFieldProps = {
  readonly label: string;
  readonly htmlFor: string;
  readonly children: ReactNode;
  readonly className?: string;
};

export function AdminFilterField({ label, htmlFor, children, className }: AdminFilterFieldProps) {
  return (
    <div className={["admin-filter-field", className].filter(Boolean).join(" ")}>
      <label className="form-label small mb-1" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  );
}

export type AdminFilterBarProps = {
  readonly children?: ReactNode;
  readonly create?: ReactNode;
};

/** Filters on one desktop line. Create sits above them at full width on a phone. */
export function AdminFilterBar({ children, create }: AdminFilterBarProps) {
  return (
    <div role="search" className="admin-filter-bar">
      {create ? <div className="admin-filter-create">{create}</div> : null}
      {children ? <div className="admin-filter-fields">{children}</div> : null}
    </div>
  );
}

export type AdminRecordTableProps = {
  /** Accessible name for the untitled card. The page or tab already shows the visible title. */
  readonly label: string;
  readonly filters?: ReactNode;
  /** Blocks between the filters and the table. */
  readonly beforeTable?: ReactNode;
  readonly children: ReactNode;
};

export function AdminRecordTable({
  label,
  filters,
  beforeTable,
  children,
}: AdminRecordTableProps) {
  return (
    <section className="card shadow-sm mb-4 admin-record-table" aria-label={label}>
      {filters ? <div className="card-body py-3 border-bottom">{filters}</div> : null}
      {beforeTable ? <div className="card-body py-3 border-bottom">{beforeTable}</div> : null}
      {children}
    </section>
  );
}
