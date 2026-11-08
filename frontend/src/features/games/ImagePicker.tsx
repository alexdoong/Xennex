import { useRef, useState } from 'react';

// Imported pictures are self-contained; no local file paths or remote URLs in game documents.
export async function prepareImage(file: File, cover: boolean): Promise<string> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw Error('Escolha uma imagem PNG, JPEG ou WebP.');
  if (file.size > 20_000_000) throw Error('Escolha uma imagem de até 20 MB.');
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width * bitmap.height > 40_000_000) throw Error('Imagem muito grande. Use uma versão menor.');
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, (cover ? 1400 : 900) / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) throw Error('Não foi possível preparar a imagem.');
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    for (const quality of [.85, .7, .5, .3]) {
      const image = canvas.toDataURL('image/webp', quality);
      if (image.length <= (cover ? 500000 : 250000)) return image;
    }
    throw Error('Esta imagem ainda ficou muito grande. Escolha uma versão menor.');
  } finally { bitmap.close(); }
}
interface Props { label: string; value: string; disabled?: boolean; cover?: boolean; onChange: (image: string) => void; onLoading?: (value: boolean) => void }
export default function ImagePicker({ label, value, disabled, cover = false, onChange, onLoading }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  return <div className="games-image-picker">
    <button type="button" className="btn secondary" disabled={disabled || loading} onClick={() => input.current?.click()}>{loading ? 'Preparando imagem…' : label}</button>
    {value && <button type="button" className="btn secondary" disabled={disabled || loading} onClick={() => onChange('')}>Remover imagem</button>}
    <input ref={input} type="file" aria-label={label} hidden accept="image/png,image/jpeg,image/webp" disabled={disabled || loading}
      onChange={async event => {
        const file = event.target.files?.[0]; event.target.value = '';
        if (!file) return;
        setLoading(true); onLoading?.(true); setError('');
        try { onChange(await prepareImage(file, cover)); } catch (e) { setError(String(e)); }
        finally { setLoading(false); onLoading?.(false); }
      }} />
    {error && <p role="alert">{error}</p>}
  </div>;
}
