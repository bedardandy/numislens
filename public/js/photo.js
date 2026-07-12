import { uploadCoinImage } from './api.js';
import { toast } from './app.js';

const KIND_LABELS = {
  obverse: 'Obverse',
  reverse: 'Reverse',
  edge: 'Edge',
  slab: 'Slab (optional)',
};

export async function downscaleImage(file, maxEdge = 2048, quality = 0.85) {
  const bitmap = await createImageBitmap(file);
  const { width, height } = bitmap;
  const longEdge = Math.max(width, height);
  const scale = longEdge > maxEdge ? maxEdge / longEdge : 1;
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h);
  bitmap.close?.();

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('Image encoding failed'))),
      'image/jpeg',
      quality,
    );
  });
}

export function renderPhotoCapture(container, accession, opts = {}) {
  const kinds = opts.kinds || ['obverse', 'reverse', 'edge', 'slab'];

  container.replaceChildren();

  const wrapper = document.createElement('div');
  wrapper.style.cssText =
    'display:flex;flex-direction:column;gap:var(--space-md);';
  container.appendChild(wrapper);

  for (const kind of kinds) {
    const slot = document.createElement('div');
    slot.style.cssText =
      'display:flex;flex-direction:column;gap:var(--space-sm);';

    const label = document.createElement('label');
    label.textContent = KIND_LABELS[kind] || kind;
    slot.appendChild(label);

    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'environment';
    slot.appendChild(input);

    const status = document.createElement('span');
    status.textContent = 'Pending';
    status.style.cssText =
      'color:var(--color-text-muted);font-size:var(--font-size-sm);';
    slot.appendChild(status);

    input.addEventListener('change', async () => {
      const file = input.files?.[0];
      if (!file) return;

      status.textContent = 'Processing…';
      status.style.color = 'var(--color-text-muted)';

      try {
        const blob = await downscaleImage(file);
        status.textContent = 'Uploading…';
        const rec = await uploadCoinImage(accession, kind, blob, kind + '.jpg');
        status.textContent = 'Uploaded';
        status.style.color = 'var(--color-success)';
        input.disabled = true;
        if (typeof opts.onUploaded === 'function') opts.onUploaded(kind, rec);
      } catch (err) {
        status.textContent = 'Failed: ' + err.message;
        status.style.color = 'var(--color-error)';
        toast(err.message, 'error');
      }
    });

    wrapper.appendChild(slot);
  }
}
