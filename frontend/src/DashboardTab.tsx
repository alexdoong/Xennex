import React from 'react';
import { Activity, ShieldCheck, Sparkles } from 'lucide-react';

interface DashboardTabProps {
  realStatus: boolean;
}

const DashboardTab: React.FC<DashboardTabProps> = ({ realStatus }) => {
  const handleStartReal = () => {
    if (window.chrome?.webview) {
      window.chrome.webview.hostObjects.api.StartReal();
    }
  };

  const handleStopReal = () => {
    if (window.chrome?.webview) {
      window.chrome.webview.hostObjects.api.StopReal();
    }
  };

  return (
    <div className="tab-content" id="dashboard-tab">
      <div className="glass-panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '24px' }}>Dashboard</h2>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Visão geral do sistema e processos em tempo real</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 14px', borderRadius: '20px', background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border-color)' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--primary)' }} />
            <span style={{ fontSize: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>Sistema Ativo</span>
          </div>
        </div>

        {/* Status Cards Grid - Adapts across full width */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginBottom: '24px' }}>
          
          {/* Real Background Process Card */}
          <div className="glass-panel-inner" style={{ margin: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: realStatus ? 'hsla(150, 90%, 50%, 0.15)' : 'hsla(350, 80%, 60%, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Activity size={18} color={realStatus ? '#00E676' : 'var(--danger)'} />
              </div>
              <div>
                <h3 style={{ fontSize: '15px', margin: 0, color: 'var(--text-primary)' }}>Processo Real Engine</h3>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Status: <strong style={{ color: realStatus ? '#00E676' : 'var(--danger)' }}>{realStatus ? 'Executando' : 'Parado'}</strong>
                </span>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '18px' }}>
              Controla os processos em segundo plano integrados para automações e drivers.
            </p>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button className="btn primary btn-glow" onClick={handleStartReal} disabled={realStatus} style={{ flex: 1 }}>
                Iniciar Motor
              </button>
              <button className="btn danger" onClick={handleStopReal} disabled={!realStatus} style={{ flex: 1 }}>
                Parar Motor
              </button>
            </div>
          </div>

          {/* Quick Info Card */}
          <div className="glass-panel-inner" style={{ margin: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'hsla(260, 100%, 65%, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Sparkles size={18} color="var(--primary)" />
              </div>
              <div>
                <h3 style={{ fontSize: '15px', margin: 0, color: 'var(--text-primary)' }}>Skin Engine & Layout</h3>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Interface adaptativa Gryphlink</span>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '18px' }}>
              Personalize o fundo, contornos de vidro e atalhos na aba de Configurações.
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderRadius: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)' }}>
              <ShieldCheck size={16} color="var(--primary)" />
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Bordas e layout calibrados com sucesso</span>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
};

export default DashboardTab;
