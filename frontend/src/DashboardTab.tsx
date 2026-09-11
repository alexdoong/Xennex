import React, { useState, useEffect } from 'react';
import { Tablet, Zap, ShieldCheck, Sparkles, RefreshCw } from 'lucide-react';
import { useToast } from './components/ToastContainer';

interface DashboardTabProps {
  realStatus: boolean;
}

const DashboardTab: React.FC<DashboardTabProps> = ({ realStatus }) => {
  const { showToast } = useToast();
  const [wacomActive, setWacomActive] = useState<boolean>(false);
  const [isWacomLoading, setIsWacomLoading] = useState<boolean>(false);

  const api = window.chrome?.webview?.hostObjects?.api;

  const checkWacomStatus = async () => {
    if (api?.IsWacomActive) {
      try {
        const active = await api.IsWacomActive();
        setWacomActive(!!active);
      } catch (e) {
        console.error('Erro ao verificar status Wacom:', e);
      }
    }
  };

  useEffect(() => {
    checkWacomStatus();
    const interval = setInterval(checkWacomStatus, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleStartReal = () => {
    if (api?.StartReal) {
      api.StartReal();
      showToast('⚡ Motor REAL de baixa latência iniciado!', 'success');
    }
  };

  const handleStopReal = () => {
    if (api?.StopReal) {
      api.StopReal();
      showToast('Motor REAL parado.', 'info');
    }
  };

  const handleEnableWacom = async () => {
    if (api?.EnableWacom) {
      setIsWacomLoading(true);
      showToast('Iniciando serviços da mesa Wacom (elevação de Admin)...', 'info');
      try {
        await api.EnableWacom();
        setTimeout(async () => {
          await checkWacomStatus();
          setIsWacomLoading(false);
          showToast('⚡ Drivers Wacom ativados com sucesso!', 'success');
        }, 3000);
      } catch (err) {
        setIsWacomLoading(false);
        showToast('Falha ao ativar drivers Wacom.', 'error');
      }
    }
  };

  const handleDisableWacom = async () => {
    if (api?.DisableWacom) {
      setIsWacomLoading(true);
      showToast('Pausando serviços da mesa Wacom...', 'warning');
      try {
        await api.DisableWacom();
        setTimeout(async () => {
          await checkWacomStatus();
          setIsWacomLoading(false);
          showToast('Drivers Wacom desativados com sucesso.', 'info');
        }, 3000);
      } catch (err) {
        setIsWacomLoading(false);
        showToast('Falha ao desativar drivers Wacom.', 'error');
      }
    }
  };

  return (
    <div className="tab-content" id="dashboard-tab">
      <div className="glass-panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '24px' }}>Dashboard Central</h2>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Controle de drivers de hardware, latência de áudio e status do sistema
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 14px', borderRadius: '20px', background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border-color)' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--primary)' }} />
            <span style={{ fontSize: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>Sistema Operante</span>
          </div>
        </div>

        {/* Status Cards Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px', marginBottom: '24px' }}>
          
          {/* Card 1: Wacom Tablet Drivers Controller */}
          <div className="glass-panel-inner" style={{ margin: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: wacomActive ? 'hsla(150, 90%, 50%, 0.15)' : 'hsla(350, 80%, 60%, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Tablet size={20} color={wacomActive ? '#00E676' : 'var(--danger)'} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '15px', margin: 0, color: 'var(--text-primary)' }}>Drivers Wacom</h3>
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      Mesa digitalizadora:{' '}
                      <strong style={{ color: wacomActive ? '#00E676' : 'var(--danger)' }}>
                        {wacomActive ? 'Ativo' : 'Inativo'}
                      </strong>
                    </span>
                  </div>
                </div>
                <button 
                  className="btn-room-link-action" 
                  style={{ minWidth: 'auto', padding: '6px 8px' }}
                  onClick={checkWacomStatus}
                  title="Atualizar status"
                >
                  <RefreshCw size={12} className={isWacomLoading ? 'spin' : ''} />
                </button>
              </div>

              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '18px', lineHeight: 1.4 }}>
                Controla o serviço <code style={{ color: 'var(--primary)', fontSize: '11px' }}>WTabletServicePro</code> e limpa instâncias presas sem abrir terminais.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button 
                className="btn primary btn-glow" 
                onClick={handleEnableWacom} 
                disabled={isWacomLoading} 
                style={{ flex: 1 }}
              >
                Ativar Drivers
              </button>
              <button 
                className="btn danger" 
                onClick={handleDisableWacom} 
                disabled={isWacomLoading} 
                style={{ flex: 1 }}
              >
                Pausar Drivers
              </button>
            </div>
          </div>

          {/* Card 2: REAL Audio Engine Controller */}
          <div className="glass-panel-inner" style={{ margin: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: realStatus ? 'hsla(150, 90%, 50%, 0.15)' : 'hsla(350, 80%, 60%, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Zap size={20} color={realStatus ? '#00E676' : 'var(--danger)'} />
                </div>
                <div>
                  <h3 style={{ fontSize: '15px', margin: 0, color: 'var(--text-primary)' }}>Motor REAL Latency</h3>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    Latência do áudio:{' '}
                    <strong style={{ color: realStatus ? '#00E676' : 'var(--danger)' }}>
                      {realStatus ? 'Em Execução' : 'Parado'}
                    </strong>
                  </span>
                </div>
              </div>

              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '18px', lineHeight: 1.4 }}>
                Reduz a latência de buffers de saída de som para sincronia perfeita em jogos de ritmo e transmissões.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button 
                className="btn primary btn-glow" 
                onClick={handleStartReal} 
                disabled={realStatus} 
                style={{ flex: 1 }}
              >
                Iniciar Motor
              </button>
              <button 
                className="btn danger" 
                onClick={handleStopReal} 
                disabled={!realStatus} 
                style={{ flex: 1 }}
              >
                Parar Motor
              </button>
            </div>
          </div>

          {/* Card 3: Skin & HUD Quick Status */}
          <div className="glass-panel-inner" style={{ margin: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'hsla(260, 100%, 65%, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Sparkles size={20} color="var(--primary)" />
                </div>
                <div>
                  <h3 style={{ fontSize: '15px', margin: 0, color: 'var(--text-primary)' }}>HUD & Glassmorphism</h3>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    Motor de Temas Adaptativo
                  </span>
                </div>
              </div>

              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '18px', lineHeight: 1.4 }}>
                Personalize imagens e vídeos de fundo, desfoque de vidro, cores de acentuação e redimensione livremente os cantos da janela.
              </p>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderRadius: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)' }}>
              <ShieldCheck size={16} color="var(--primary)" />
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                Janela fluida sem quebra de transparência
              </span>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
};

export default DashboardTab;
