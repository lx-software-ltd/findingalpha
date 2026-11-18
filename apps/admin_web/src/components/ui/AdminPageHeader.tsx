import type { ReactNode } from "react";

export type AdminPageHeaderProps = {
  readonly eyebrow?: string;
  readonly title: string;
  readonly children?: ReactNode;
};

/** Page title row. The eyebrow names the product; actions sit on the right. */
export function AdminPageHeader({ eyebrow, title, children }: AdminPageHeaderProps) {
  return (
    <header className="admin-page-header">
      <div>
        {eyebrow ? <p className="admin-eyebrow">{eyebrow}</p> : null}
        <div className="admin-page-title-row">
          <h1 className="admin-page-title">{title}</h1>
        </div>
      </div>
      {children ? <div className="admin-page-actions">{children}</div> : null}
    </header>
  );
}
