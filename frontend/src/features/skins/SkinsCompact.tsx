import { useEffect, useState, useRef } from 'react';
import { Palette, Maximize2 } from 'lucide-react';
import type { SkinConfig } from '../../webview';
import { normalizeSkinConfig } from '../../utils/skinUtils';
import type { AppTab } from '../../layout/navigation';

type Props = {
  activeSkinName: string;
  editing: boolean;
  onSkinUpdated: (skin: SkinConfig) => void;
  onEditSkin: (name: string) => void;
  openFullWindow: (tab?: AppTab) => void;
};

export default function SkinsCompact({ activeSkinName, editing, onSkinUpdated, onEditSkin, openFullWindow }: Props) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [available, setAvailable] = useState<string[]>([]);

  useEffect(() => {
    api?.GetAvailableSkins().then(list => setAvailable(list ?? []))
      .catch(() => setError('Não foi possível listar as skins.'));
  }, [api, activeSkinName]);

  return (
    <div className="compact-module-view compact-skins">
      <div className="compact-skin-picker">
        <label htmlFor="compact-skin-select">Skin ativa</label>
        <select
          id="compact-skin-select"
          value={activeSkinName}
          disabled={busy || editing}
          onChange={async e => {
            const name = e.target.value;
            if (!api) return;
            setBusy(true); setError('');
            try {
              const config = normalizeSkinConfig(JSON.parse(await api.GetSkinConfig(name)));
              await api.SetActiveSkin(name);
              onSkinUpdated(config);
            } catch { setError('Não foi possível aplicar a skin.'); }
            finally { setBusy(false); }
          }}
        >
          {available.map(name => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
      </div>

      {error && <p role="alert" className="compact-error">{error}</p>}
      <p className="compact-hint">Edite cores, fundo, opacidades e layout aqui, com prévia ao vivo. Salve uma cópia para personalizar a skin padrão.</p>
      <div className="compact-skin-actions">
        <button
          className="btn primary w-full"
          onClick={() => {
            onEditSkin(activeSkinName);
          }}
        >
          <Palette size={14} /> Editar skin no compacto
        </button>
      </div>

      <button
        className="compact-expand-link"
        onClick={() => {
          openFullWindow();
          onEditSkin(activeSkinName);
        }}
      >
        <Maximize2 size={13} />
        <span>Abrir estúdio de skins e temas</span>
      </button>
    </div>
  );
}
