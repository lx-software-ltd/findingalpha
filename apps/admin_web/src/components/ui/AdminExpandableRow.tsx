import { createContext, useContext, useId, useRef, type MouseEvent, type ReactNode } from "react";
import { markRecordGroup } from "../../lib/recordGroup";

export type AdminExpandableRowProps = {
  readonly colSpan: number;
  readonly expanded: boolean;
  readonly onToggle: () => void;
  readonly children: ReactNode;
  readonly editor: ReactNode;
};

type ExpandContextValue = {
  readonly expanded: boolean;
  readonly detailId: string;
  readonly onToggle: () => void;
};

const ExpandContext = createContext<ExpandContextValue | null>(null);

function selectionInside(row: HTMLElement): boolean {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return false;
  if (selection.toString().trim().length === 0) return false;
  const node = selection.anchorNode;
  return node !== null && row.contains(node);
}

/** Disclosure control for one expandable record. Screen readers and keyboards use this, not the row. */
export function AdminExpandButton({ children }: { readonly children: ReactNode }) {
  const ctx = useContext(ExpandContext);
  if (!ctx) {
    throw new Error("AdminExpandButton must be rendered inside AdminExpandableRow");
  }
  return (
    <button
      type="button"
      className="btn btn-link p-0 text-decoration-none fw-semibold"
      aria-expanded={ctx.expanded}
      aria-controls={ctx.expanded ? ctx.detailId : undefined}
      onClick={(event) => {
        event.stopPropagation();
        ctx.onToggle();
      }}
    >
      {children}
    </button>
  );
}

/**
 * One record: a summary row plus, when open, a detail row.
 * Each record is its own `<tbody>` so the open editor stays with that record.
 * Pointer users can click the row. Keyboard and screen-reader users use `AdminExpandButton`.
 * Dragging to select text inside the row does not toggle. The editor is not rendered while closed.
 */
export function AdminExpandableRow({
  colSpan,
  expanded,
  onToggle,
  children,
  editor,
}: AdminExpandableRowProps) {
  const detailId = useId();
  const pointerDown = useRef<{ x: number; y: number } | null>(null);

  function toggleFromRow(row: HTMLElement) {
    if (selectionInside(row)) return;
    onToggle();
  }

  function onMouseDown(event: MouseEvent<HTMLTableRowElement>) {
    pointerDown.current = { x: event.clientX, y: event.clientY };
  }

  function onClick(event: MouseEvent<HTMLTableRowElement>) {
    const down = pointerDown.current;
    pointerDown.current = null;
    if (down) {
      const moved = Math.abs(event.clientX - down.x) > 4 || Math.abs(event.clientY - down.y) > 4;
      if (moved) return;
    }
    toggleFromRow(event.currentTarget);
  }

  return (
    <tbody className="admin-record-group">
      <ExpandContext.Provider value={{ expanded, detailId, onToggle }}>
        <tr
          className={expanded ? "admin-expand-summary admin-row-framed" : "admin-expand-summary"}
          onMouseDown={onMouseDown}
          onClick={onClick}
        >
          {children}
        </tr>
      </ExpandContext.Provider>
      {expanded ? (
        <tr id={detailId} className="admin-expand-detail admin-row-detail-framed">
          <td colSpan={colSpan} className="p-0">
            <div className="admin-expand is-open">
              <div className="admin-expand-inner p-3" onClick={(event) => event.stopPropagation()}>
                {editor}
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </tbody>
  );
}

markRecordGroup(AdminExpandableRow);
