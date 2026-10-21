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
