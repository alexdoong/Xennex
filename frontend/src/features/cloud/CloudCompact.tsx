import { useState } from 'react';
import { Cloud, Check, RefreshCw, Maximize2 } from 'lucide-react';
import type { AppTab } from '../../layout/navigation';

type Props = {
  openFullWindow: (tab?: AppTab) => void;
};

export default function CloudCompact({ openFullWindow }: Props) {
  const api = window.chrome?.webview?.hostObjects?.api;
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');
  const [projectId, setProjectId] = useState('');

  useState(() => {
    api?.GetCloudProjectId?.().then(id => setProjectId(id || '')).catch(() => {});
  });

  const testConnection = async () => {
    setStatus('testing');
    try {
      const key = await api?.GetCloudApiKey?.();
      if (key && projectId) {
        setStatus('ok');
      } else {
        setStatus('error');
      }
    } catch {
      setStatus('error');
    }
  };

  return (
    <div className="compact-module-view compact-cloud">
      <div className="compact-cloud-box">
        <Cloud size={24} />
        <div className="compact-cloud-meta">
          <strong>Nuvem BYOD</strong>
          <span>{projectId ? `Projeto: ${projectId}` : 'Nenhum projeto configurado'}</span>
        </div>
      </div>

      <div className="compact-cloud-actions">
        <button className="btn secondary w-full" onClick={() => void testConnection()}>
          <RefreshCw size={14} /> Testar conexão
        </button>
        {status === 'ok' && <p className="compact-hint text-success"><Check size={13} /> Conexão ativa.</p>}
        {status === 'error' && <p className="compact-error">Configure a chave de API na aba Cloud.</p>}
      </div>

      <button
        className="compact-expand-link"
        onClick={() => openFullWindow('cloud')}
      >
        <Maximize2 size={13} />
        <span>Abrir sincronização e banco de dados completo</span>
      </button>
    </div>
  );
}
