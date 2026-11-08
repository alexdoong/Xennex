import { useState, useRef, useEffect } from 'react';
import { ArrowLeft, Maximize2, Minus, Pin, PinOff } from 'lucide-react';
import type { AppTab } from './navigation';
import CompactPanel from './CompactPanel';
import { useCompactInteraction } from '../hooks/useCompactInteraction';
import LocalAiCompact from '../features/local-ai/LocalAiCompact';
import StreamCompact from '../features/stream/StreamCompact';
import GamesCompact from '../features/games/GamesCompact';
import AssetsCompact from '../features/assets/AssetsCompact';
import GesturesCompact from '../features/hand-motion/GesturesCompact';
import CloudCompact from '../features/cloud/CloudCompact';
import SettingsCompact from '../features/settings/SettingsCompact';
import SkinsCompact from '../features/skins/SkinsCompact';
import type { useAppState } from '../hooks/useAppState';

type Props = ReturnType<typeof useAppState> & {
  activeTab: AppTab;
  setActiveTab: (tab: AppTab) => void;
  openFullWindow: (tab?: AppTab) => void;
};

export type CompactView = 'home' | AppTab | 'skin-editor';

const VIEW_TITLES: Record<string, string> = {
  dashboard: 'Início',
  'wuwa-db': 'Jogos',
  assets: 'Biblioteca',
  'local-ai': 'IA local',
  cloud: 'Cloud',
  stream: 'Transmissões',
  'hand-motion': 'Gestures',
  settings: 'Configurações',
  'skin-editor': 'Aparência'
};

export default function CompactWorkspace(props: Props) {
  const { activeTab, setActiveTab, openFullWindow, sidebarPosition, activeSkinName,
    realStatus, handMotionStatus, autoHideSidebar, setAutoHideSidebar, autoHideTitlebar,
    setAutoHideTitlebar, closeToTray, setCloseToTray, onEditSkin } = props;

  const [compactView, setCompactView] = useState<CompactView>('home');
  useCompactInteraction(true, compactView);
  const [pinned, setPinned] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;

  useEffect(() => {
    api?.IsSidebarPinned().then(setPinned).catch(e => setError(String(e)));
  }, [api]);

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await action();
    } catch {
      setError('Não foi possível alterar o painel.');
    } finally {
      setBusy(false);
    }
  }

  const navigateTo = (view: CompactView) => {
    setCompactView(view === 'dashboard' ? 'home' : view);
    if (view !== 'home' && view !== 'skin-editor') {
      setActiveTab(view);
    }
  };

  const handleExpand = () => {
    if (compactView !== 'home' && compactView !== 'skin-editor') {
      openFullWindow(compactView);
    } else {
      openFullWindow(activeTab);
    }
  };

  return (
    <section className="compact-panel" aria-label="Painel compacto">
      <header className="compact-header">
        {compactView === 'home' ? (
          <div>
            <span className="compact-eyebrow">SEU ESPAÇO, POR PERTO</span>
            <h1>Xennex</h1>
          </div>
        ) : (
          <div className="compact-sub-header">
            <button
              className="title-btn compact-back-btn"
              onClick={() => setCompactView('home')}
              title="Voltar ao início"
              aria-label="Voltar ao início"
            >
              <ArrowLeft size={17} />
            </button>
            <h1>{VIEW_TITLES[compactView] || 'Xennex'}</h1>
          </div>
        )}

        <div className="compact-actions">
          <button
            className="title-btn"
            aria-label="Manter painel aberto"
            aria-pressed={pinned}
            disabled={busy}
            title={pinned ? 'Permitir recolhimento automático' : 'Manter painel aberto'}
            onClick={() => run(async () => {
              await api?.SetSidebarPinned(!pinned);
              setPinned(!pinned);
            })}
          >
            {pinned ? <PinOff size={17} /> : <Pin size={17} />}
          </button>
          <button
            className="title-btn"
            aria-label="Minimizar para a bandeja"
            onClick={() => run(async () => { await api?.MinimizeToTray(); })}
          >
            <Minus size={17} />
          </button>
          <button
            className="title-btn"
            aria-label="Expandir Xennex"
            title="Voltar à janela completa"
            onClick={handleExpand}
          >
            <Maximize2 size={17} />
          </button>
        </div>
      </header>

      {error && <p role="alert" className="compact-error">{error}</p>}

      <div className="compact-body">
        {compactView === 'home' && (
          <CompactPanel
            activeTab={activeTab}
            position={sidebarPosition}
            skinName={activeSkinName}
            realStatus={realStatus}
            handMotionStatus={handMotionStatus}
            onNavigate={navigateTo}
            onOpenFull={openFullWindow}
          />
        )}
        {compactView === 'local-ai' && <LocalAiCompact openFullWindow={openFullWindow} />}
        {compactView === 'stream' && <StreamCompact openFullWindow={openFullWindow} />}
        {compactView === 'wuwa-db' && <GamesCompact openFullWindow={openFullWindow} />}
        {compactView === 'assets' && <AssetsCompact openFullWindow={openFullWindow} />}
        {compactView === 'hand-motion' && <GesturesCompact openFullWindow={openFullWindow} />}
        {compactView === 'cloud' && <CloudCompact openFullWindow={openFullWindow} />}
        {compactView === 'settings' && (
          <SettingsCompact
            position={sidebarPosition}
            autoHideSidebar={autoHideSidebar}
            setAutoHideSidebar={setAutoHideSidebar}
            autoHideTitlebar={autoHideTitlebar}
            setAutoHideTitlebar={setAutoHideTitlebar}
            closeToTray={closeToTray}
            setCloseToTray={setCloseToTray}
            openFullWindow={openFullWindow}
          />
        )}
        {compactView === 'skin-editor' && (
          <SkinsCompact
            activeSkinName={activeSkinName}
            onSkinUpdated={props.onSkinUpdated}
            editing={props.skinEditorName !== null}
            onEditSkin={onEditSkin}
            openFullWindow={openFullWindow}
          />
        )}
      </div>

      <footer className="compact-footer">
        <span className="compact-skin" title={activeSkinName}>Skin · {activeSkinName}</span>
        <p>{pinned ? 'Painel fixado. Seus espaços continuam ativos.' : 'Afaste o cursor para recolher. Aproxime da alça para voltar.'}</p>
      </footer>
    </section>
  );
}
