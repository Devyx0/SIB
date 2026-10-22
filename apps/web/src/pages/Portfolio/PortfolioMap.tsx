import { useEffect, useRef } from 'react';
import { LngLatBounds, Map as MapLibreMap, Marker, NavigationControl, ScaleControl, setWorkerUrl } from 'maplibre-gl';
// MapLibre finds its worker relative to its own file, which Vite moves; build it explicitly.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import styles from './MapView.module.css';

// Free, keyless OpenStreetMap-based vector tiles (OpenFreeMap). Override with
// VITE_MAP_STYLE_URL to use another MapLibre style (MapTiler, Stadia, self-hosted…).
const STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL
  ?? 'https://tiles.openfreemap.org/styles/positron';

/** Below this zoom the map shows one bubble per sector; above it, every building. */
const BUILDING_ZOOM = 10.5;
const QUEBEC: [number, number] = [-71.2, 46.8];

setWorkerUrl(workerUrl);

export type MapPin = {
  id: number; lat: number; lng: number; color: string; label: string; sectorId: number;
};
export type MapBubble = {
  id: number; lat: number; lng: number; color: string; label: string; count: number;
};

type Props = {
  pins: MapPin[];
  /** One bubble per sector, shown when zoomed out. Empty = always show pins. */
  bubbles: MapBubble[];
  selectedId: number | null;
  onSelectBuilding: (id: number | null) => void;
  onSelectSector: (id: number) => void;
  /** Change it to re-frame the map on the current pins (scope changed). */
  fitKey: string;
};

function el(className: string, html = ''): HTMLDivElement {
  const d = document.createElement('div');
  d.className = className;
  if (html) d.innerHTML = html;
  return d;
}

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

export default function PortfolioMap({ pins, bubbles, selectedId, onSelectBuilding, onSelectSector, fitKey }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const pinEls = useRef(new Map<number, HTMLElement>());
  const cb = useRef({ onSelectBuilding, onSelectSector });
  cb.current = { onSelectBuilding, onSelectSector };
  const grouped = bubbles.length > 0;

  // Create the map once.
  useEffect(() => {
    if (!host.current) return;
    const m = new MapLibreMap({
      container: host.current,
      style: STYLE_URL,
      center: QUEBEC,
      zoom: 6,
      attributionControl: { compact: true },
      cooperativeGestures: false,
    });
    m.addControl(new NavigationControl({ showCompass: false }), 'top-right');
    m.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-right');
    m.on('click', () => cb.current.onSelectBuilding(null));
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  // (Re)build markers whenever the data changes.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];
    pinEls.current.clear();

    const container = m.getContainer();
    const applyLevel = () => {
      container.dataset.level = grouped && m.getZoom() < BUILDING_ZOOM ? 'sectors' : 'buildings';
    };

    for (const p of pins) {
      const e = el(styles.pin, `<span class="${styles.pinDot}"></span>`);
      e.style.setProperty('--pin', p.color);
      e.title = p.label;
      e.setAttribute('role', 'button');
      e.setAttribute('aria-label', p.label);
      e.addEventListener('click', (ev) => { ev.stopPropagation(); cb.current.onSelectBuilding(p.id); });
      pinEls.current.set(p.id, e);
      markers.current.push(new Marker({ element: e, anchor: 'center' }).setLngLat([p.lng, p.lat]).addTo(m));
    }
    for (const b of bubbles) {
      const e = el(styles.bubble, `<span class="${styles.bubbleBody}"><span class="${styles.bubbleCount}">${b.count}</span><span class="${styles.bubbleName}">${escapeHtml(b.label)}</span></span>`);
      e.style.setProperty('--pin', b.color);
      e.setAttribute('role', 'button');
      e.setAttribute('aria-label', `${b.label} (${b.count})`);
      e.addEventListener('click', (ev) => { ev.stopPropagation(); cb.current.onSelectSector(b.id); });
      markers.current.push(new Marker({ element: e, anchor: 'center' }).setLngLat([b.lng, b.lat]).addTo(m));
    }

    applyLevel();
    m.on('zoom', applyLevel);
    return () => { m.off('zoom', applyLevel); };
  }, [pins, bubbles, grouped]);

  // Frame the data on first load and whenever the scope changes.
  useEffect(() => {
    const m = map.current;
    if (!m || pins.length === 0) return;
    const b = new LngLatBounds();
    pins.forEach((p) => b.extend([p.lng, p.lat]));
    m.fitBounds(b, { padding: { top: 70, bottom: 70, left: 70, right: 70 }, maxZoom: 15, duration: 700 });
  }, [fitKey, pins.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Highlight the selected building and bring it into view.
  useEffect(() => {
    pinEls.current.forEach((e, id) => e.classList.toggle(styles.pinSelected, id === selectedId));
    const m = map.current;
    const p = selectedId != null ? pins.find((x) => x.id === selectedId) : null;
    if (m && p) {
      m.getContainer().dataset.level = 'buildings';
      m.easeTo({ center: [p.lng, p.lat], zoom: Math.max(m.getZoom(), 14), duration: 600 });
    }
  }, [selectedId, pins]);

  return <div ref={host} className={styles.canvas} data-testid="portfolio-map" />;
}
