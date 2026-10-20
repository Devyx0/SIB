// Shrink a picked photo in the browser before it is sent: longest side
// capped, re-encoded as JPEG. Keeps a 12-megapixel phone photo to a few
// hundred KB so the new-call request stays light.

export interface EncodedPhoto {
  mime: 'image/jpeg' | 'image/png' | 'image/webp';
  data_base64: string;
}

const KEEP_AS_IS_BYTES = 600 * 1024;
const SENDABLE = new Set(['image/jpeg', 'image/png', 'image/webp']);

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = String(r.result);
      resolve(s.slice(s.indexOf(',') + 1));
    };
    r.onerror = () => reject(new Error('unreadable file'));
    r.readAsDataURL(file);
  });
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('unreadable image')); };
    img.src = url;
  });
}

export async function shrinkImage(file: File, maxSide = 1600, quality = 0.85): Promise<EncodedPhoto> {
  const img = await loadImage(file);
  const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
  // Already small and a format the server takes: re-encoding would only add bytes.
  if (scale === 1 && file.size <= KEEP_AS_IS_BYTES && SENDABLE.has(file.type)) {
    return { mime: file.type as EncodedPhoto['mime'], data_base64: await readBase64(file) };
  }
  const w = Math.max(1, Math.round(img.naturalWidth * scale));
  const h = Math.max(1, Math.round(img.naturalHeight * scale));
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas unavailable');
  ctx.fillStyle = '#fff'; // transparent PNGs become white, not black
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);
  const dataUrl = canvas.toDataURL('image/jpeg', quality);
  return { mime: 'image/jpeg', data_base64: dataUrl.slice(dataUrl.indexOf(',') + 1) };
}
