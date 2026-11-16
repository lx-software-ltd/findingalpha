export type AdminNavItem = {
  readonly to: string;
  readonly label: string;
  readonly icon?: string;
  readonly mark?: string;
  readonly end?: boolean;
};

export const ADMIN_NAV_GROUPS: readonly (readonly AdminNavItem[])[] = [
  [
    { to: "/", label: "Roadmap", icon: "bi-signpost-split", end: true },
    { to: "/system", label: "System", icon: "bi-activity" },
    { to: "/methodology", label: "Methodology", icon: "bi-journal-check" },
    { to: "/screen", label: "Screen", icon: "bi-funnel" },
  ],
];
