import React, { useState, useEffect } from 'react';
import { ArrowLeft, ArrowRight, ArrowUp, ArrowDown, Keyboard, Check, X, Camera, Play, Square, Sparkles } from 'lucide-react';

interface HandMotionTabProps {
  handMotionStatus: boolean;
}

const HandMotionTab: React.FC<HandMotionTabProps> = ({ handMotionStatus }) => {
  const [cameraIndex, setCameraIndex] = useState<number>(0);
  const [selectedAction, setSelectedAction] = useState<string>('KEYBOARD:alt+tab');
  const [isRecordingGesture, setIsRecordingGesture] = useState<boolean>(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [savedGestures, setSavedGestures] = useState<string[]>([]);
  const [swipeConfig, setSwipeConfig] = useState<Record<string, string>>({
    SwipeLeft: '', SwipeRight: '', SwipeUp: '', SwipeDown: ''
  });

  // Key recording state
  const [recordingTarget, setRecordingTarget] = useState<string | null>(null);
  const [currentKeyPreview, setCurrentKeyPreview] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  const api = window.chrome?.webview?.hostObjects?.api;

  const fetchGestures = () => {
    if (api) {
      api.GetSavedGestures()
        .then((gestures: string[]) => {
          if (gestures) setSavedGestures(gestures);
        })
        .catch((e: any) => console.error(e));

      api.GetSwipeConfig()
        .then((json: string) => {
          try {
            const parsed = JSON.parse(json || '{}');
            setSwipeConfig({
              SwipeLeft: parsed.SwipeLeft || '',
              SwipeRight: parsed.SwipeRight || '',
              SwipeUp: parsed.SwipeUp || '',
              SwipeDown: parsed.SwipeDown || ''
            });
          } catch(e) {}
        })
        .catch((e: any) => console.error(e));
    }
  };

  useEffect(() => {
    if (api) {
      api.GetHandMotionCameraIndex().then(idx => setCameraIndex(idx || 0));
    }
    fetchGestures();
  }, []);

  // Keyboard shortcut capture listener
  useEffect(() => {
    if (!recordingTarget) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const modifiers: string[] = [];
      if (e.metaKey) modifiers.push('win');
      if (e.ctrlKey) modifiers.push('ctrl');
      if (e.altKey) modifiers.push('alt');
      if (e.shiftKey) modifiers.push('shift');

      const rawKey = e.key.toLowerCase();

      // Cancel on Escape alone
      if ((rawKey === 'escape' || rawKey === 'esc') && modifiers.length === 0) {
        setRecordingTarget(null);
        setCurrentKeyPreview(null);
        return;
      }

      // If only a modifier was pressed, preview it and wait for main key
      if (['control', 'alt', 'shift', 'meta', 'os'].includes(rawKey)) {
        setCurrentKeyPreview(modifiers.join(' + ') + ' + ...');
        return;
      }

      let key = rawKey;
      if (key === 'arrowleft') key = 'left';
      else if (key === 'arrowright') key = 'right';
      else if (key === 'arrowup') key = 'up';
      else if (key === 'arrowdown') key = 'down';
      else if (key === 'escape') key = 'esc';
      else if (key === 'enter') key = 'enter';
      else if (key === ' ') key = 'space';
      else if (key === 'delete') key = 'del';
      else if (key === 'backspace') key = 'backspace';

      const parts = [...modifiers.filter(m => m !== key), key];
      const combo = parts.join('+');
      const actionString = `KEYBOARD:${combo}`;

      if (recordingTarget === 'custom') {
        setSelectedAction(actionString);
        triggerFeedback(`Atalho "${combo}" selecionado!`);
      } else {
        const newSwipeConfig = { ...swipeConfig, [recordingTarget]: actionString };
        setSwipeConfig(newSwipeConfig);
        if (api) {
          api.SaveSwipeConfig(JSON.stringify(newSwipeConfig));
        }
        triggerFeedback(`Atalho "${combo}" salvo para ${recordingTarget}!`);
      }

      setRecordingTarget(null);
      setCurrentKeyPreview(null);
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => {
      window.removeEventListener('keydown', handleKeyDown, true);
    };
  }, [recordingTarget, swipeConfig]);

  const triggerFeedback = (msg: string) => {
    setFeedbackMessage(msg);
    setTimeout(() => {
      setFeedbackMessage(null);
    }, 3000);
  };

  const handleStart = () => {
    api?.StartHandMotion();
  };

  const handleStop = () => {
    api?.StopHandMotion();
  };

  const handleCameraChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value) || 0;
    setCameraIndex(val);
    api?.SetHandMotionCameraIndex(val);
  };

  const handleRecordGesture = () => {
    if (!handMotionStatus) {
      alert("Inicie o Gesture OS primeiro!");
      return;
    }
    
    setCountdown(3);
    let count = 3;
    const interval = setInterval(() => {
      count -= 1;
      setCountdown(count);
      if (count <= 0) {
        clearInterval(interval);
        api?.StartRecordingGesture(selectedAction);
        setIsRecordingGesture(true);
      }
    }, 1000);
  };

  const handleStopRecordingGesture = () => {
    api?.StopRecordingGesture();
    setIsRecordingGesture(false);
    setTimeout(fetchGestures, 500);
  };

  const handleSaveSwipeConfig = () => {
    if (api) {
      api.SaveSwipeConfig(JSON.stringify(swipeConfig));
      triggerFeedback("Configurações de swipe salvas com sucesso!");
    }
  };

  const handleRecordSwipePose = () => {
    if (!handMotionStatus) {
      alert("Inicie o Gesture OS primeiro!");
      return;
    }
    
    setIsRecordingGesture(true);
    setCountdown(3);
    api?.RecordHandGesture("SwipeMode");

    let count = 3;
    const interval = setInterval(() => {
      count -= 1;
      setCountdown(count);
      if (count <= 0) {
        clearInterval(interval);
        setTimeout(() => {
          setIsRecordingGesture(false);
          fetchGestures();
        }, 1000); 
      }
    }, 1000);
  };

  const handleDeleteGesture = (gestureName: string) => {
    api?.DeleteGesture(gestureName);
    setTimeout(fetchGestures, 500);
  };

  const applyPreset = (direction: string, action: string) => {
    const newConfig = { ...swipeConfig, [direction]: action };
    setSwipeConfig(newConfig);
    if (api) {
      api.SaveSwipeConfig(JSON.stringify(newConfig));
    }
    triggerFeedback(`Preset "${action.replace('KEYBOARD:', '')}" aplicado!`);
  };

  const swipeDirections = [
    { id: 'SwipeLeft', label: 'Swipe Left', desc: 'Mover mão para a esquerda', icon: <ArrowLeft size={18} /> },
    { id: 'SwipeRight', label: 'Swipe Right', desc: 'Mover mão para a direita', icon: <ArrowRight size={18} /> },
    { id: 'SwipeUp', label: 'Swipe Up', desc: 'Mover mão para cima', icon: <ArrowUp size={18} /> },
    { id: 'SwipeDown', label: 'Swipe Down', desc: 'Mover mão para baixo', icon: <ArrowDown size={18} /> }
  ];

  return (
    <div className="tab-content hand-motion-tab" id="hand-motion-tab">
      <div className="glass-panel">
        
        {/* Header & Status */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              Gesture OS
              <Sparkles size={20} color="var(--primary)" />
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: handMotionStatus ? 'var(--primary)' : 'var(--danger)', boxShadow: handMotionStatus ? '0 0 10px var(--primary-glow)' : 'none' }}></div>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                {handMotionStatus ? `Ativo na Câmera ${cameraIndex}` : 'Desconectado'}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Camera size={16} color="var(--text-secondary)" />
              <input 
                type="number" 
                className="modern-input" 
                style={{ width: '60px', padding: '6px 10px', textAlign: 'center' }}
                value={cameraIndex} 
                onChange={handleCameraChange}
                min={0}
                disabled={handMotionStatus}
                title="Índice da Câmera"
              />
            </div>

            <button 
              className="btn primary btn-glow" 
              onClick={handleStart}
              disabled={handMotionStatus}
              style={{ padding: '8px 16px', fontSize: '13px' }}
            >
              <Play size={14} /> Iniciar
            </button>
            <button 
              className="btn danger" 
              onClick={handleStop}
              disabled={!handMotionStatus}
              style={{ padding: '8px 16px', fontSize: '13px' }}
            >
              <Square size={14} /> Parar
            </button>
          </div>
        </div>

        {/* Floating Notification */}
        {feedbackMessage && (
          <div style={{ 
            background: 'rgba(99, 102, 241, 0.2)', 
            border: '1px solid var(--primary)', 
            color: 'white', 
            padding: '10px 16px', 
            borderRadius: '12px', 
            marginBottom: '20px', 
            fontSize: '13px', 
            display: 'flex', 
            alignItems: 'center', 
            gap: '8px',
            animation: 'fadeIn 0.2s ease-out'
          }}>
            <Check size={16} color="var(--primary)" />
            {feedbackMessage}
          </div>
        )}

        {/* Dynamic Swipes Section */}
        <div className="glass-panel-inner">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <h3 style={{ fontSize: '16px', color: 'var(--primary)' }}>Atalhos de Movimento (Dynamic Swipes)</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '12px', marginTop: '2px' }}>
                Vincule atalhos do Windows aos movimentos. Você pode <b>pressionar as teclas diretamente no teclado</b> ou <b>digitar manualmente</b>.
              </p>
            </div>
            
            <button 
              className="btn primary" 
              onClick={handleRecordSwipePose}
              disabled={isRecordingGesture || !handMotionStatus}
              style={{ fontSize: '12px', padding: '6px 14px' }}
            >
              Gravar Pose de Ativação
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
            {swipeDirections.map(({ id, label, desc, icon }) => {
              const isRecordingThis = recordingTarget === id;
              const currentValue = swipeConfig[id] || '';

              return (
                <div 
                  key={id} 
                  style={{ 
                    background: isRecordingThis ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255, 255, 255, 0.04)', 
                    border: isRecordingThis ? '1px solid var(--danger)' : '1px solid var(--border)', 
                    borderRadius: '12px', 
                    padding: '12px 16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                    transition: 'var(--transition)'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ 
                        background: 'rgba(255,255,255,0.08)', 
                        padding: '6px', 
                        borderRadius: '8px', 
                        display: 'flex', 
                        alignItems: 'center', 
                        color: 'var(--primary)' 
                      }}>
                        {icon}
                      </div>
                      <div>
                        <span style={{ fontWeight: 600, fontSize: '14px', display: 'block' }}>{label}</span>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{desc}</span>
                      </div>
                    </div>

                    {/* Action Controls */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: '1', maxWidth: '420px', justifyContent: 'flex-end' }}>
                      {/* Manual input */}
                      <input 
                        type="text" 
                        className="modern-input" 
                        style={{ flex: 1, padding: '8px 12px', fontSize: '13px', fontFamily: 'monospace' }}
                        placeholder="e.g. KEYBOARD:win+left"
                        value={currentValue}
                        onChange={(e) => setSwipeConfig({ ...swipeConfig, [id]: e.target.value })}
                        disabled={isRecordingThis}
                      />

                      {/* Interactive Key Record Button */}
                      <button 
                        className={`btn ${isRecordingThis ? 'danger btn-glow' : 'primary'}`}
                        style={{ fontSize: '12px', padding: '8px 14px', whiteSpace: 'nowrap', minWidth: '130px' }}
                        onClick={() => {
                          if (isRecordingThis) {
                            setRecordingTarget(null);
                            setCurrentKeyPreview(null);
                          } else {
                            setRecordingTarget(id);
                            setCurrentKeyPreview(null);
                          }
                        }}
                      >
                        {isRecordingThis ? (
                          currentKeyPreview ? currentKeyPreview : '🔴 Pressione teclas...'
                        ) : (
                          <><Keyboard size={14} /> Pressionar Tecla</>
                        )}
                      </button>

                      {currentValue && (
                        <button 
                          className="btn" 
                          style={{ padding: '8px', background: 'rgba(255,255,255,0.08)', color: 'var(--text-secondary)' }}
                          onClick={() => {
                            const newConfig = { ...swipeConfig, [id]: '' };
                            setSwipeConfig(newConfig);
                            if (api) api.SaveSwipeConfig(JSON.stringify(newConfig));
                          }}
                          title="Limpar atalho"
                        >
                          <X size={14} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Quick Presets row */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', paddingTop: '4px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)', marginRight: '4px' }}>Sugestões rápidas:</span>
                    <button className="btn" style={{ padding: '3px 8px', fontSize: '11px', background: 'rgba(255,255,255,0.06)' }} onClick={() => applyPreset(id, 'KEYBOARD:win+left')}>
                      Win + Seta Esquerda
                    </button>
                    <button className="btn" style={{ padding: '3px 8px', fontSize: '11px', background: 'rgba(255,255,255,0.06)' }} onClick={() => applyPreset(id, 'KEYBOARD:win+right')}>
                      Win + Seta Direita
                    </button>
                    <button className="btn" style={{ padding: '3px 8px', fontSize: '11px', background: 'rgba(255,255,255,0.06)' }} onClick={() => applyPreset(id, 'KEYBOARD:win+up')}>
                      Win + Seta Cima
                    </button>
                    <button className="btn" style={{ padding: '3px 8px', fontSize: '11px', background: 'rgba(255,255,255,0.06)' }} onClick={() => applyPreset(id, 'KEYBOARD:alt+tab')}>
                      Alt + Tab
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
            <button 
              className="btn primary btn-glow" 
              onClick={handleSaveSwipeConfig}
              style={{ fontSize: '13px', padding: '8px 20px' }}
            >
              Salvar Alterações
            </button>
          </div>
        </div>

        {/* Custom Gestures Section */}
        <div className="glass-panel-inner" style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '16px', color: 'var(--primary)', marginBottom: '8px' }}>Gestos Estáticos Personalizados</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '12px', marginBottom: '16px' }}>
            Grave uma pose de mão única para acionar comandos lógicos ou atalhos de teclado.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', marginBottom: '16px' }}>
            <div className="input-group">
              <label>Tipo de Gesto</label>
              <select 
                className="modern-input" 
                value={selectedAction.startsWith('KEYBOARD:') ? 'keyboard' : 'custom'}
                onChange={(e) => {
                  if (e.target.value === 'keyboard') {
                    setSelectedAction('KEYBOARD:alt+tab');
                  } else {
                    setSelectedAction('MoveMouse');
                  }
                }}
                disabled={isRecordingGesture || !handMotionStatus}
              >
                <option value="keyboard">Atalho de Teclado (Keyboard Shortcut)</option>
                <option value="custom">Ação do Sistema (MoveMouse, MoveWindow)</option>
              </select>
            </div>

            <div className="input-group">
              <label>{selectedAction.startsWith('KEYBOARD:') ? 'Atalho a ser executado' : 'Nome da Ação'}</label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input 
                  type="text"
                  className="modern-input" 
                  value={selectedAction.startsWith('KEYBOARD:') ? selectedAction.replace('KEYBOARD:', '') : selectedAction} 
                  onChange={(e) => {
                    if (selectedAction.startsWith('KEYBOARD:')) {
                      setSelectedAction('KEYBOARD:' + e.target.value);
                    } else {
                      setSelectedAction(e.target.value);
                    }
                  }}
                  disabled={isRecordingGesture || !handMotionStatus || recordingTarget === 'custom'}
                  placeholder={selectedAction.startsWith('KEYBOARD:') ? 'e.g. win+left' : 'e.g. MoveMouse'}
                  style={{ flex: 1, fontFamily: selectedAction.startsWith('KEYBOARD:') ? 'monospace' : 'inherit' }}
                />

                {selectedAction.startsWith('KEYBOARD:') && (
                  <button 
                    className={`btn ${recordingTarget === 'custom' ? 'danger btn-glow' : 'primary'}`}
                    style={{ fontSize: '12px', padding: '8px 14px', whiteSpace: 'nowrap' }}
                    onClick={() => {
                      if (recordingTarget === 'custom') {
                        setRecordingTarget(null);
                        setCurrentKeyPreview(null);
                      } else {
                        setRecordingTarget('custom');
                        setCurrentKeyPreview(null);
                      }
                    }}
                  >
                    {recordingTarget === 'custom' ? (
                      currentKeyPreview ? currentKeyPreview : '🔴 Pressione teclas...'
                    ) : (
                      <><Keyboard size={14} /> Pressionar</>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>

          {!isRecordingGesture ? (
            <button 
              className="btn primary btn-glow" 
              onClick={handleRecordGesture}
              disabled={!handMotionStatus || !selectedAction}
            >
              Gravar Pose da Mão para este Gesto
            </button>
          ) : (
            <button 
              className="btn danger btn-glow" 
              onClick={handleStopRecordingGesture} 
              style={{ animation: 'pulse 1s infinite' }}
            >
              {countdown !== null && countdown > 0 ? `Prepare a mão... ${countdown}` : "Finalizar Gravação"}
            </button>
          )}

          {/* Saved Gestures List */}
          <div style={{ marginTop: '24px' }}>
            <h4 style={{ fontSize: '14px', color: 'var(--text-primary)', marginBottom: '12px' }}>Gestos Gravados</h4>
            {savedGestures.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Nenhum gesto gravado ainda.</p>
            ) : (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {savedGestures.map((gesture) => {
                  const displayName = gesture.startsWith('KEYBOARD:') 
                    ? `⌨️ Atalho: ${gesture.replace('KEYBOARD:', '')}`
                    : `⚙️ Sistema: ${gesture}`;
                  
                  return (
                    <li key={gesture} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(255,255,255,0.05)', padding: '8px 14px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <span style={{ fontSize: '13px', fontWeight: 500 }}>{displayName}</span>
                      <button 
                        className="btn danger" 
                        style={{ padding: '4px 10px', fontSize: '12px' }}
                        onClick={() => handleDeleteGesture(gesture)}
                      >
                        Excluir
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};

export default HandMotionTab;
