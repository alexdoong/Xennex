import { Play, Square, Shield, ShieldAlert, Maximize2 } from 'lucide-react';
import { useGesturesContext } from './GesturesContext';
import type { AppTab } from '../../layout/navigation';

type Props = {
  openFullWindow: (tab?: AppTab) => void;
};

export default function GesturesCompact({ openFullWindow }: Props) {
  const { api, status, camera, busy, run } = useGesturesContext();

  return (
    <div className="compact-module-view compact-gestures">
      <div className="compact-gesture-status-box">
        <span className="compact-status-tag" data-armed={status.armed} data-running={status.running}>
          {status.armed ? 'CONTROLANDO O PC' : status.running ? 'MODO DE TESTE' : 'CÂMERA DESLIGADA'}
        </span>
        <p>{status.message || 'Controle de gestos em espera.'}</p>
        <div className="compact-gesture-detail">
          <span>Mão: {status.hand === 'Left' ? 'Esquerda' : status.hand === 'Right' ? 'Direita' : '—'}</span>
          <span>Gesto: <strong>{status.match || 'aguardando'}</strong></span>
        </div>
      </div>

      <div className="compact-gesture-controls">
        <button
          className={`btn ${status.running ? 'secondary' : 'primary'} w-full`}
          disabled={!api || busy}
          onClick={() => void run(async () => {
            if (status.running) await api!.StopHandMotion();
            else { await api!.SetHandMotionCameraIndex(camera); await api!.StartHandMotion(); }
          })}
        >
          {status.running ? <><Square size={14} /> Desligar câmera</> : <><Play size={14} /> Ligar câmera</>}
        </button>

        <button
          className={`btn ${status.armed ? 'warning' : 'outline'} w-full`}
          disabled={!api || !status.running || busy}
          onClick={() => void run(async () => {
            await api!.SetGestureControl(!status.armed);
          })}
        >
          {status.armed ? <><ShieldAlert size={14} /> Desarmar controle</> : <><Shield size={14} /> Armar controle do PC</>}
        </button>
      </div>

      <button
        className="compact-expand-link"
        onClick={() => openFullWindow('hand-motion')}
      >
        <Maximize2 size={13} />
        <span>Configurar gestos, macros e ações</span>
      </button>
    </div>
  );
}
