// Inline icons for the portfolio's view / edit / add actions.

type P = { size?: number };

const base = (size: number) => ({
  viewBox: '0 0 20 20', width: size, height: size, 'aria-hidden': true as const,
  fill: 'none', stroke: 'currentColor', strokeWidth: 1.8,
  strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
});

export function PencilIcon({ size = 16 }: P) {
  return <svg {...base(size)}><path d="M13.5 3.5l3 3L7 16H4v-3l9.5-9.5z" /><path d="M11.5 5.5l3 3" /></svg>;
}

export function EyeIcon({ size = 16 }: P) {
  return (
    <svg {...base(size)}>
      <path d="M1.5 10S4.5 4.5 10 4.5 18.5 10 18.5 10 15.5 15.5 10 15.5 1.5 10 1.5 10z" />
      <circle cx="10" cy="10" r="2.5" />
    </svg>
  );
}

export function PlusIcon({ size = 16 }: P) {
  return <svg {...base(size)}><path d="M10 4v12M4 10h12" /></svg>;
}

export function TrashIcon({ size = 16 }: P) {
  return <svg {...base(size)}><path d="M3.5 5.5h13M8 5.5V4h4v1.5M5.5 5.5l.8 10.5h7.4l.8-10.5" /></svg>;
}

export function LinkOutIcon({ size = 14 }: P) {
  return <svg {...base(size)}><path d="M11 3.5h5.5V9M16.5 3.5L9 11M14 12v4.5H3.5V6H8" /></svg>;
}

export function PhoneIcon({ size = 16 }: P) {
  return (
    <svg {...base(size)} viewBox="0 0 24 24" strokeWidth={1.9}>
      <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />
    </svg>
  );
}

export function MailIcon({ size = 16 }: P) {
  return (
    <svg {...base(size)} viewBox="0 0 24 24" strokeWidth={1.9}>
      <rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" />
    </svg>
  );
}

// Header fact icons (20px, same stroke as the rest).
const fact = (size: number) => ({ ...base(size), strokeWidth: 1.6 });

export function FolderIcon({ size = 20 }: P) {
  return <svg {...fact(size)}><path d="M2.5 5.5a1 1 0 0 1 1-1h4l1.5 2h7.5a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-13a1 1 0 0 1-1-1z" /></svg>;
}

export function BuildingIcon({ size = 20 }: P) {
  return (
    <svg {...fact(size)}>
      <path d="M4 17.5V3.5h8v14M12 8h4v9.5M2.5 17.5h15M7 6.5h2M7 9.5h2M7 12.5h2M14 11h.01M14 14h.01" />
    </svg>
  );
}

export function HomeIcon({ size = 20 }: P) {
  return <svg {...fact(size)}><path d="M2.5 9.5L10 3l7.5 6.5" /><path d="M4.5 8v9h11V8" /><path d="M8.5 17v-5h3v5" /></svg>;
}

export function UsersIcon({ size = 20 }: P) {
  return (
    <svg {...fact(size)}>
      <circle cx="8" cy="7" r="3" /><path d="M2.5 16.5c.6-3 2.8-4.5 5.5-4.5s4.9 1.5 5.5 4.5" />
      <path d="M13 4.2a3 3 0 0 1 0 5.6M15 12.3c1.3.6 2.2 2 2.5 4.2" />
    </svg>
  );
}

export function LayersIcon({ size = 20 }: P) {
  return <svg {...fact(size)}><path d="M10 3l7.5 4-7.5 4-7.5-4z" /><path d="M2.5 11l7.5 4 7.5-4" /></svg>;
}

export function CalendarIcon({ size = 20 }: P) {
  return <svg {...fact(size)}><rect x="3" y="4.5" width="14" height="12.5" rx="1.5" /><path d="M3 8.5h14M7 3v3M13 3v3" /></svg>;
}

export function HashIcon({ size = 20 }: P) {
  return <svg {...fact(size)}><path d="M8 3L6.5 17M13.5 3L12 17M3.5 7.5h14M2.5 12.5h14" /></svg>;
}

export function MapPinIcon({ size = 20 }: P) {
  return <svg {...fact(size)}><path d="M10 17.5s5.5-5 5.5-9.5a5.5 5.5 0 0 0-11 0c0 4.5 5.5 9.5 5.5 9.5z" /><circle cx="10" cy="8" r="2" /></svg>;
}

// Portfolio totals strip (24px).
export function CityIcon({ size = 24 }: P) {
  return (
    <svg {...fact(size)}>
      <path d="M3 17.5V7.5l5-2v12M8 17.5V3h7v14.5M15 8.5h2.5v9M1.5 17.5h17" />
      <path d="M10.5 6h2M10.5 9h2M10.5 12h2M5 10h1M5 13h1" />
    </svg>
  );
}

export function DocumentIcon({ size = 24 }: P) {
  return (
    <svg {...fact(size)}>
      <rect x="4" y="2.5" width="12" height="15" rx="1.5" /><path d="M7 7h6M7 10h6M7 13h4" />
    </svg>
  );
}

export function PieIcon({ size = 24 }: P) {
  return <svg {...fact(size)}><path d="M10 2.5a7.5 7.5 0 1 0 7.5 7.5H10z" /><path d="M12.5 2.9a7.5 7.5 0 0 1 4.6 4.6h-4.6z" /></svg>;
}

export function GridIcon({ size = 18 }: P) {
  return <svg {...base(size)}><rect x="3" y="3" width="5.5" height="5.5" rx="1" /><rect x="11.5" y="3" width="5.5" height="5.5" rx="1" /><rect x="3" y="11.5" width="5.5" height="5.5" rx="1" /><rect x="11.5" y="11.5" width="5.5" height="5.5" rx="1" /></svg>;
}

export function ListIcon({ size = 18 }: P) {
  return <svg {...base(size)}><path d="M7 5h10M7 10h10M7 15h10M3.5 5h.01M3.5 10h.01M3.5 15h.01" /></svg>;
}
