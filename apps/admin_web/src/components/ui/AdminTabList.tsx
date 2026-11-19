import { useId, useRef, type KeyboardEvent } from "react";
import { adminTabButtonId, nextTabIdForKey } from "../../lib/adminTabs";

export type AdminTabItem<T extends string> = {
  readonly id: T;
  readonly label: string;
};

export type AdminTabListProps<T extends string> = {
  readonly tabs: readonly AdminTabItem<T>[];
  readonly active: T;
  readonly onChange: (id: T) => void;
  readonly className?: string;
  /** Accessible name of the list, e.g. "Screen sections". */
  readonly label: string;
  /**
   * Stable prefix for tab button ids. Pass the same value to
   * `adminTabButtonId(prefix, active)` for the panel's `aria-labelledby`.
   */
  readonly idPrefix?: string;
  /** `id` of the element that renders the active tab's content. */
  readonly panelId?: string;
  /** When all controls should be non-interactive (e.g. data failed to load). */
  readonly disabled?: boolean;
};

/**
 * Page-section switcher following the WAI-ARIA Tabs pattern (automatic
 * activation, roving tabindex, arrow/Home/End keys).
 */
export function AdminTabList<T extends string>({
  tabs,
  active,
  onChange,
  className = "mb-4",
  label,
  idPrefix,
  panelId,
  disabled = false,
}: AdminTabListProps<T>) {
  const generated = useId();
  const prefix = idPrefix ?? generated;
  const buttonRefs = useRef(new Map<T, HTMLButtonElement>());
  const ids = tabs.map((tab) => tab.id);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const next = nextTabIdForKey(event.key, ids, active);
    if (!next) return;
    event.preventDefault();
    onChange(next);
    buttonRefs.current.get(next)?.focus();
  };

  return (
    <div className={`admin-tab-list-wrap ${className}`.trim()}>
      <ul className="nav admin-tab-list" role="tablist" aria-label={label}>
        {tabs.map((item) => {
          const isActive = item.id === active;
          return (
            <li key={item.id} className="nav-item" role="presentation">
              <button
                ref={(element) => {
                  if (element) buttonRefs.current.set(item.id, element);
                  else buttonRefs.current.delete(item.id);
                }}
                id={adminTabButtonId(prefix, item.id)}
                type="button"
                className={`nav-link admin-tab ${isActive ? "active" : ""}`.trim()}
                role="tab"
                aria-selected={isActive}
                aria-controls={panelId}
                aria-disabled={disabled || undefined}
                tabIndex={isActive ? 0 : -1}
                disabled={disabled}
                onClick={() => onChange(item.id)}
                onKeyDown={onKeyDown}
              >
                <span>{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
