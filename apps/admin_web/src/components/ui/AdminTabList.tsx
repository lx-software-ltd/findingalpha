export type AdminTab = { readonly id: string; readonly label: string };

export function AdminTabList<T extends string>({
  tabs,
  value,
  onChange,
}: {
  readonly tabs: readonly AdminTab[];
  readonly value: T;
  readonly onChange: (id: T) => void;
}) {
  return (
    <ul className="nav nav-tabs mb-3" role="tablist">
      {tabs.map((tab) => (
        <li className="nav-item" key={tab.id} role="presentation">
          <button
            type="button"
            className={`nav-link${value === tab.id ? " active" : ""}`}
            role="tab"
            aria-selected={value === tab.id}
            onClick={() => onChange(tab.id as T)}
          >
            {tab.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
