import { useRef, useState } from 'react';
import { ArrowUpRight, Palette } from 'lucide-react';
import { APP_TABS, type AppTab } from './navigation';
import CompactPlacement from './CompactPlacement';
import type { CompactView } from './CompactWorkspace';

type Props = {
  activeTab: AppTab;
  position: string;
  skinName: string;
  realStatus: boolean;
  handMotionStatus: boolean;
  onNavigate: (view: CompactView) => void;
  onOpenFull: (tab?: AppTab) => void;
};

const labels: Record<AppTab, string> = {
  dashboard: 'Início',
  'wuwa-db': 'Jogos',
  assets: 'Biblioteca',
  'local-ai': 'IA local',
  cloud: 'Cloud',
  stream: 'Transmissões',
  'hand-motion': 'Gestures',
  settings: 'Configurações',
};

export default function CompactPanel({
  activeTab,
  position,
  realStatus,
  handMotionStatus,
  onNavigate,
  onOpenFull: _onOpenFull
}: Props) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="compact-scroll">
      <button
        className="compact-resume"
        onClick={() => onNavigate(activeTab)}
      >
        <span>
          <small>CONTINUAR DE ONDE PAROU</small>
          <strong>{labels[activeTab]}</strong>
        </span>
        <ArrowUpRight size={23} />
      </button>

      <div className="compact-section-heading">
        <h2>Acesso rápido</h2>
        <span>Abra seu espaço</span>
      </div>

      <nav className="compact-grid" aria-label="Atalhos do Xennex">
        {APP_TABS.map(({ id, icon: Icon }) => (
          <button
            key={id}
            className="compact-shortcut"
            aria-label={`Abrir ${labels[id]}`}
            onClick={() => onNavigate(id)}
          >
            <span className="compact-shortcut-icon"><Icon size={21} /></span>
            <span>{labels[id]}</span>
          </button>
        ))}
        <button className="compact-shortcut" onClick={() => onNavigate('skin-editor')}>
          <span className="compact-shortcut-icon"><Palette size={21} /></span>
          <span>Aparência</span>
        </button>
      </nav>

      <div className="compact-status" aria-label="Serviços">
        <span><i data-active={realStatus} />REAL {realStatus ? 'ativo' : 'parado'}</span>
        <span><i data-active={handMotionStatus} />Gestures {handMotionStatus ? 'ativo' : 'parado'}</span>
      </div>

      <label className="compact-position">Posição na tela
        <select
          value={position}
          disabled={busy}
          onChange={e => {
            const next = e.target.value;
            void run(async () => {
              await api?.SetSidebarPosition(next);
              window.updateSidebarPosition?.(next);
            });
          }}
        >
          <option value="MiddleRight">Direita</option>
          <option value="MiddleLeft">Esquerda</option>
          <option value="TopLeft">Canto superior esquerdo</option>
        </select>
      </label>

      <CompactPlacement position={position} />
    </div>
  );
}
