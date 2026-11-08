import CompactPlacement from '../../layout/CompactPlacement';
import { Maximize2 } from 'lucide-react';
import type { AppTab } from '../../layout/navigation';

type Props = {
  position: string;
  autoHideSidebar: boolean;
  setAutoHideSidebar: (v: boolean) => void;
  autoHideTitlebar: boolean;
  setAutoHideTitlebar: (v: boolean) => void;
  closeToTray: boolean;
  setCloseToTray: (v: boolean) => void;
  openFullWindow: (tab?: AppTab) => void;
};

export default function SettingsCompact({
  position,
  autoHideSidebar,
  setAutoHideSidebar,
  autoHideTitlebar,
  setAutoHideTitlebar,
  closeToTray,
  setCloseToTray,
  openFullWindow
}: Props) {
  const api = window.chrome?.webview?.hostObjects?.api;

  return (
    <div className="compact-module-view compact-settings">
      <CompactPlacement position={position} />

      <div className="compact-settings-group">
        <h4>Comportamento</h4>
        <label className="compact-checkbox">
          <input
            type="checkbox"
            checked={autoHideSidebar}
            onChange={e => {
              const val = e.target.checked;
              setAutoHideSidebar(val);
              api?.SetAutoHideSidebar?.(val);
            }}
          />
          <span>Ocultar automaticamente a barra</span>
        </label>

        <label className="compact-checkbox">
          <input
            type="checkbox"
            checked={autoHideTitlebar}
            onChange={e => {
              const val = e.target.checked;
              setAutoHideTitlebar(val);
              api?.SetAutoHideTitlebar?.(val);
            }}
          />
          <span>Ocultar barra de título</span>
        </label>

        <label className="compact-checkbox">
          <input
            type="checkbox"
            checked={closeToTray}
            onChange={e => {
              const val = e.target.checked;
              setCloseToTray(val);
              api?.SetCloseToTray?.(val);
            }}
          />
          <span>Minimizar para bandeja do sistema</span>
        </label>
      </div>

      <button
        className="compact-expand-link"
        onClick={() => openFullWindow('settings')}
      >
        <Maximize2 size={13} />
        <span>Abrir todas as configurações</span>
      </button>
    </div>
  );
}
