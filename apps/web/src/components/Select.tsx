import {
  Children, isValidElement, useCallback, useEffect, useId, useLayoutEffect, useRef, useState,
} from 'react';
import type { ReactElement, ReactNode, SelectHTMLAttributes } from 'react';
import { createPortal } from 'react-dom';
import { Avatar } from './Avatar';
import styles from './Select.module.css';

// Themed drop-in for <select>. Same props, same <option> children, same
// onChange(event) contract: a visually hidden native <select> stays the
// source of truth (value, form semantics, data-testid), and the themed list
// writes to it and fires a real "change" event — so existing handlers keep
// working unchanged. The list is portalled to <body> so modals with
// overflow never clip it.

interface Opt {
  value: string;
  label: ReactNode;
  text: string;
  disabled: boolean;
}

function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return '';
}

function collectOptions(children: ReactNode): Opt[] {
  const out: Opt[] = [];
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return;
    const el = child as ReactElement<{ value?: string | number; disabled?: boolean; children?: ReactNode }>;
    if (el.type === 'option') {
      const label = el.props.children;
      out.push({
        value: el.props.value != null ? String(el.props.value) : textOf(label),
        label,
        text: textOf(label),
        disabled: !!el.props.disabled,
      });
    } else if (el.props.children) {
      out.push(...collectOptions(el.props.children));
    }
  });
  return out;
}

const setNativeValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set;

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  children: ReactNode;
  /** A search box at the top of the open list (long lists such as employees). */
  searchable?: boolean;
  searchPlaceholder?: string;
  noResultsText?: string;
  /** An initials disc before each option and the chosen value (people lists). */
  avatars?: boolean;
};

/** Accent- and case-insensitive, so « andre » finds « André ». */
const fold = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

export default function Select({
  className = '', children, value, defaultValue, disabled, id, onChange, style,
  'aria-label': ariaLabel, searchable = false, searchPlaceholder = 'Rechercher…',
  noResultsText = 'Aucun résultat', avatars = false, ...rest
}: Props) {
  const options = collectOptions(children);
  const [query, setQuery] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);
  const visible = options.map((_, i) => i).filter((i) => !query || fold(options[i].text).includes(fold(query)));
  const nativeRef = useRef<HTMLSelectElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const autoId = useId();
  const triggerId = id ?? `sel-${autoId}`;
  const listId = `${triggerId}-list`;

  const current = value != null ? String(value) : undefined;
  const [uncontrolled, setUncontrolled] = useState(defaultValue != null ? String(defaultValue) : options[0]?.value);
  const selectedValue = current ?? uncontrolled;
  const selected = options.find((o) => o.value === selectedValue) ?? options[0];

  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [pos, setPos] = useState<{ top: number; left: number; width: number; up: boolean } | null>(null);
  const typeBuf = useRef({ text: '', at: 0 });

  // Labels pointing at our id should also name the trigger.
  const [labelText, setLabelText] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (ariaLabel || !id) return;
    const safe = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(id) : id;
    const lab = document.querySelector(`label[for="${safe}"]`);
    if (lab) setLabelText(lab.textContent ?? undefined);
  }, [ariaLabel, id]);

  const place = useCallback(() => {
    const r = triggerRef.current?.getBoundingClientRect();
    if (!r) return;
    const spaceBelow = window.innerHeight - r.bottom;
    const up = spaceBelow < 240 && r.top > spaceBelow;
    setPos({ top: up ? r.top : r.bottom, left: r.left, width: r.width, up });
  }, []);

  function openList() {
    if (disabled) return;
    place();
    const idx = options.findIndex((o) => o.value === selected?.value);
    setActive(idx >= 0 ? idx : options.findIndex((o) => !o.disabled));
    setQuery('');
    setOpen(true);
  }

  // Search box takes focus when the list opens.
  useEffect(() => {
    if (open && searchable) searchRef.current?.focus();
  }, [open, searchable]);

  function close(focusTrigger = true) {
    setOpen(false);
    if (focusTrigger) triggerRef.current?.focus();
  }

  function choose(o: Opt) {
    if (o.disabled) return;
    const el = nativeRef.current;
    if (current == null) setUncontrolled(o.value);
    if (el && o.value !== el.value) {
      setNativeValue?.call(el, o.value);
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    close();
  }

  // Keep the list attached to the trigger while open.
  useLayoutEffect(() => {
    if (!open) return;
    const onMove = () => place();
    window.addEventListener('resize', onMove);
    window.addEventListener('scroll', onMove, true);
    return () => {
      window.removeEventListener('resize', onMove);
      window.removeEventListener('scroll', onMove, true);
    };
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || listRef.current?.contains(t)) return;
      setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  useEffect(() => {
    if (!open || active < 0) return;
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView?.({ block: 'nearest' });
  }, [open, active]);

  /** Next enabled option among the ones the search leaves visible. */
  function step(from: number, dir: 1 | -1): number {
    if (visible.length === 0) return -1;
    let pos = visible.indexOf(from);
    if (pos < 0) pos = dir === 1 ? -1 : visible.length;
    for (let n = 0; n < visible.length; n++) {
      pos = (pos + dir + visible.length) % visible.length;
      if (!options[visible[pos]].disabled) return visible[pos];
    }
    return from;
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (disabled) return;
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault();
        openList();
      }
      return;
    }
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); setActive((a) => step(a, 1)); break;
      case 'ArrowUp': e.preventDefault(); setActive((a) => step(a, -1)); break;
      case 'Home': if (!searchable) { e.preventDefault(); setActive(step(-1, 1)); } break;
      case 'End': if (!searchable) { e.preventDefault(); setActive(step(options.length, -1)); } break;
      case ' ':
      case 'Enter':
        if (e.key === ' ' && searchable) break; // a space typed into the search box
        e.preventDefault();
        if (options[active] && visible.includes(active)) choose(options[active]);
        break;
      case 'Escape':
        // Close the list only — not the dialog it sits in.
        e.preventDefault();
        e.stopPropagation();
        close();
        break;
      case 'Tab':
        setOpen(false);
        break;
      default:
        if (!searchable && e.key.length === 1 && !e.metaKey && !e.ctrlKey) {
          const now = Date.now();
          const buf = now - typeBuf.current.at > 600 ? e.key : typeBuf.current.text + e.key;
          typeBuf.current = { text: buf, at: now };
          const hit = options.findIndex((o) => !o.disabled && o.text.toLowerCase().startsWith(buf.toLowerCase()));
          if (hit >= 0) setActive(hit);
        }
    }
  }

  return (
    <span className={styles.wrap} style={style}>
      <select
        {...rest}
        ref={nativeRef}
        value={current}
        defaultValue={current == null ? defaultValue : undefined}
        disabled={disabled}
        onChange={(e) => {
          if (current == null) setUncontrolled(e.target.value);
          onChange?.(e);
        }}
        className={styles.native}
        tabIndex={-1}
        aria-hidden="true"
      >
        {children}
      </select>
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        aria-label={ariaLabel ?? labelText}
        disabled={disabled}
        className={`${className} ${styles.trigger}`}
        onClick={() => (open ? close() : openList())}
        onKeyDown={onKeyDown}
      >
        {/* Every label is stacked in one cell so the field keeps the width of
            the longest option, like a native select — only the chosen one shows. */}
        <span className={styles.value}>
          {options.map((o, i) => (
            <span key={`${o.value}-${i}`} className={o === selected ? styles.shown : styles.sizer} aria-hidden={o === selected ? undefined : true}>
              {avatars && o.value !== '' ? <span className={styles.withAvatar}><Avatar name={o.text} size="xs" />{o.label}</span> : o.label}
            </span>
          ))}
        </span>
      </button>
      {open && pos && createPortal(
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-labelledby={triggerId}
          className={`${styles.list} ${pos.up ? styles.up : ''}`}
          style={{
            left: pos.left,
            minWidth: pos.width,
            ...(pos.up ? { bottom: window.innerHeight - pos.top + 4 } : { top: pos.top + 4 }),
          }}
          onKeyDown={onKeyDown}
        >
          {searchable && (
            <li role="presentation" className={styles.searchRow}>
              <input
                ref={searchRef}
                type="search"
                className={styles.search}
                value={query}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                aria-controls={listId}
                aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
                autoComplete="off"
                onChange={(e) => {
                  const q = e.target.value;
                  setQuery(q);
                  const first = options.findIndex((o) => !o.disabled && (!q || fold(o.text).includes(fold(q))));
                  setActive(first);
                }}
                onKeyDown={(e) => { e.stopPropagation(); onKeyDown(e); }}
                data-testid="select-search"
              />
            </li>
          )}
          {searchable && visible.length === 0 && (
            <li role="presentation" className={styles.noResults}>{noResultsText}</li>
          )}
          {visible.map((i) => options[i]).map((o, n) => { const i = visible[n]; return (
            <li
              key={`${o.value}-${i}`}
              id={`${listId}-${i}`}
              data-index={i}
              role="option"
              aria-selected={o.value === selected?.value}
              aria-disabled={o.disabled || undefined}
              className={[
                styles.option,
                i === active ? styles.active : '',
                o.value === selected?.value ? styles.selected : '',
                o.disabled ? styles.disabled : '',
              ].join(' ')}
              onMouseEnter={() => !o.disabled && setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(o)}
            >
              {avatars && o.value !== '' && <Avatar name={o.text} size="xs" />}
              <span className={styles.optionText}>{o.label}</span>
              {o.value === selected?.value && (
                <svg className={styles.check} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4.5 10.5l3.5 3.5 7.5-8" />
                </svg>
              )}
            </li>
          ); })}
        </ul>,
        document.body,
      )}
    </span>
  );
}
