import type { ReactNode } from "react";

export type AdminEditorSectionProps = {
  readonly title?: string;
  readonly description?: string;
  readonly children: ReactNode;
};

/**
 * Section card: a title, then the body.
 * Use for blocks that sit above or below a record table.
 */
export function AdminEditorSection({ title, description, children }: AdminEditorSectionProps) {
  return (
    <div className="card shadow-sm mb-4">
      <div className="card-body">
        {title ? <h2 className="admin-card-title">{title}</h2> : null}
        {description ? <p className="small text-muted mb-3">{description}</p> : null}
        {children}
      </div>
    </div>
  );
}
