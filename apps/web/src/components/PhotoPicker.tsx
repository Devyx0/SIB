import { useRef } from 'react';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './PhotoPicker.module.css';

// Photo tiles with a dashed « Ajouter des photos » tile: one wide button when
// empty, a square tile beside the thumbnails after that. Each thumbnail has
// its own remove button. Used by the new call form and the public request.

export type PickedPhoto = { file: File; url: string };

interface Props {
  lang: Lang;
  photos: PickedPhoto[];
  onChange: (photos: PickedPhoto[]) => void;
  max?: number;
  /** id of the visible label naming the photo group. */
  labelledBy?: string;
}

export default function PhotoPicker({ lang, photos, onChange, max = 5, labelledBy }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  function add(list: FileList | null) {
    if (!list) return;
    const picked = Array.from(list).filter((f) => f.type.startsWith('image/'));
    onChange([
      ...photos,
      ...picked.slice(0, max - photos.length).map((file) => ({ file, url: URL.createObjectURL(file) })),
    ]);
    if (inputRef.current) inputRef.current.value = '';
  }

  function remove(i: number) {
    URL.revokeObjectURL(photos[i].url);
    onChange(photos.filter((_, j) => j !== i));
  }

  return (
    <>
      <div className={styles.grid} role="group" aria-labelledby={labelledBy}>
        {photos.map((p, i) => (
          <div key={p.url} className={styles.tile}>
            <img src={p.url} alt={t(lang, `Photo ${i + 1}`, `Photo ${i + 1}`)} />
            <button
              type="button"
              className={styles.remove}
              onClick={() => remove(i)}
              aria-label={t(lang, `Retirer la photo ${i + 1}`, `Remove photo ${i + 1}`)}
            >
              <svg viewBox="0 0 20 20" width="12" height="12" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
          </div>
        ))}
        {photos.length < max && (
          <button
            type="button"
            className={styles.add}
            onClick={() => inputRef.current?.click()}
            data-testid="add-photo"
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" />
            </svg>
            <span>{photos.length ? t(lang, 'Ajouter', 'Add') : t(lang, 'Ajouter des photos', 'Add photos')}</span>
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/*"
        multiple
        hidden
        onChange={(e) => add(e.target.files)}
        data-testid="photo-input"
      />
    </>
  );
}
