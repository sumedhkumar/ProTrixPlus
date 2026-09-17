const paths = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  layers: "m12 3 10 5-10 5L2 8l10-5z M2 12l10 5 10-5 M2 16l10 5 10-5",
  shield: "M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4z m-4 9 3 3 5-6",
  arrow: "M4 12h16 m-6-6 6 6-6 6",
  wallet: "M20 8V5H5a2 2 0 0 1 0-4h13 M3 3v16a2 2 0 0 0 2 2h16V8H5 M21 12h-6v5h6",
  activity: "M2 12h4l3-8 6 16 3-8h4",
  signal: "M4 18v3 M9 13v8 M14 8v13 M19 3v18",
  logout: "M9 3H3v18h6 M9 12h12 m-4-4 4 4-4 4",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  close: "m6 6 12 12 M6 18 18 6",
  lock: "M5 10h14v11H5z M8 10V6a4 4 0 0 1 8 0v4",
  check: "m5 12 4 4L19 6",
  clock: "M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  user: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-2a8 8 0 0 1 16 0v2",
  server: "M3 3h18v7H3z M3 14h18v7H3z M7 6.5h.01 M7 17.5h.01 M11 6.5h6 M11 17.5h6",
} as const;

export type IconName = keyof typeof paths;

export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}><path d={paths[name]} /></svg>;
}

export function Brand() {
  return <span className="brand"><span className="brand-mark" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M4 17V7h6v10H4Zm10 0V3h6v14h-6Z" fill="currentColor" /><path d="M4 21h16" stroke="currentColor" strokeWidth="2" /></svg></span><span>ProTrix<span className="brand-plus">Plus</span><span className="brand-period">.</span></span></span>;
}
