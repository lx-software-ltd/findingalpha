/** A row component with this flag renders its own `<tbody>`. */
export function markRecordGroup<T>(component: T): T {
  (component as { recordGroup?: boolean }).recordGroup = true;
  return component;
}

/** True for the component or a `memo` / `forwardRef` wrapper around it. */
export function hasRecordGroup(type: unknown, depth = 0): boolean {
  if (depth > 4 || type == null) return false;
  if (typeof type !== "function" && typeof type !== "object") return false;
  const typed = type as { recordGroup?: boolean; type?: unknown; render?: unknown };
  if (typed.recordGroup === true) return true;
  if (typed.type != null && typed.type !== type && hasRecordGroup(typed.type, depth + 1)) return true;
  if (typeof typed.render === "function" && typed.render !== type && hasRecordGroup(typed.render, depth + 1)) {
    return true;
  }
  return false;
}
