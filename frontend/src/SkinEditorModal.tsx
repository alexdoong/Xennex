import React, { useState, useEffect } from 'react';
import type { SkinConfig } from './webview';
import { 
  X, Image as ImageIcon, Video, Palette, Sliders, FolderOpen, 
  RotateCcw, Check, Sparkles, Layout, Monitor, Square 
} from 'lucide-react';

interface SkinEditorModalProps {
  skinName: string;
  isOpen: boolean;
  onClose: () => void;
  onSaved: (updatedConfig: SkinConfig) => void;
}

const DEFAULT_CONFIG: SkinConfig = {
  name: 'default',
  backgroundType: 'image',
  backgroundUrl: 'https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=1920&auto=format&fit=crop',
  backgroundColor: '#0f131a',
  backgroundOpacity: 1.0,
  backgroundBlur: 0,
  sidebarImage: '',
  sidebarColor: 'hsla(220, 20%, 12%, 0.7)',
  titlebarImage: '',
  titlebarColor: 'hsla(220, 20%, 12%, 0.7)',
  primaryColor: 'hsl(260, 100%, 65%)',
  primaryHover: 'hsl(260, 100%, 75%)',
  textColor: 'hsl(220, 10%, 95%)',
  borderColor: 'rgba(255, 255, 255, 0.25)',
  borderOpacity: 0.25,
  borderWidth: 1
};

const COLOR_PRESETS = [
  { name: 'Gryphline Purple', color: 'hsl(260, 100%, 65%)', hover: 'hsl(260, 100%, 75%)' },
  { name: 'Cyber Cyan', color: 'hsl(185, 100%, 50%)', hover: 'hsl(185, 100%, 60%)' },
  { name: 'Crimson Red', color: 'hsl(350, 85%, 60%)', hover: 'hsl(350, 85%, 70%)' },
  { name: 'Amber Gold', color: 'hsl(45, 100%, 55%)', hover: 'hsl(45, 100%, 65%)' },
  { name: 'Emerald Green', color: 'hsl(150, 90%, 50%)', hover: 'hsl(150, 90%, 60%)' },
  { name: 'Sakura Pink', color: 'hsl(330, 90%, 65%)', hover: 'hsl(330, 90%, 75%)' },
  { name: 'Silver Frost', color: 'hsl(215, 20%, 85%)', hover: 'hsl(215, 20%, 95%)' }
];

const BORDER_PRESETS = [
  { name: '⚪ Gryphlink Branco', color: '#ffffff', opacity: 0.25, width: 1 },
  { name: '💎 Vidro Cristalino', color: '#ffffff', opacity: 0.45, width: 1 },
  { name: '🟣 Roxo Gryphline', color: 'hsl(260, 100%, 65%)', opacity: 0.4, width: 1 },
  { name: '🔵 Ciano Cyber', color: 'hsl(185, 100%, 50%)', opacity: 0.4, width: 1 },
  { name: '🟡 Dourado Glow', color: 'hsl(45, 100%, 55%)', opacity: 0.35, width: 1 },
  { name: '🌑 Escuro Sutil', color: 'rgba(0, 0, 0, 0.6)', opacity: 0.6, width: 1 }
];

const SkinEditorModal: React.FC<SkinEditorModalProps> = ({
  skinName,
  isOpen,
  onClose,
  onSaved
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'background' | 'bars' | 'borders' | 'colors'>('background');
  const [config, setConfig] = useState<SkinConfig>({ ...DEFAULT_CONFIG, name: skinName });
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  const api = window.chrome?.webview?.hostObjects?.api;

  useEffect(() => {
    if (!isOpen) return;

    const loadConfig = async () => {
      setLoading(true);
      try {
        if (api) {
          const json = await api.GetSkinConfig(skinName);
          if (json && json.trim() !== '{}' && json.trim() !== '') {
            const parsed = JSON.parse(json);
            setConfig({ ...DEFAULT_CONFIG, ...parsed, name: skinName });
          } else {
            setConfig({ ...DEFAULT_CONFIG, name: skinName });
          }
        }
      } catch (err) {
        console.error('Failed to load skin config:', err);
        setConfig({ ...DEFAULT_CONFIG, name: skinName });
      } finally {
        setLoading(false);
      }
    };

    loadConfig();
  }, [isOpen, skinName]);

  if (!isOpen) return null;

  const showToast = (msg: string) => {
    setStatusMsg(msg);
    setTimeout(() => setStatusMsg(''), 3500);
  };

  const handlePickAsset = async (assetType: 'image' | 'video', targetField: 'backgroundUrl' | 'sidebarImage' | 'titlebarImage') => {
    if (!api) return;
    try {
      const url = await api.PickAndImportAsset(skinName, assetType);
      if (url) {
        setConfig(prev => ({
          ...prev,
          [targetField]: url,
          ...(targetField === 'backgroundUrl' ? { backgroundType: assetType } : {})
        }));
        showToast('Arquivo importado com sucesso!');
      }
    } catch (err) {
      console.error('Pick asset error:', err);
      showToast('Erro ao importar arquivo.');
    }
  };

  const handleSave = async () => {
    if (!api) return;
    setLoading(true);
    try {
      const json = JSON.stringify(config, null, 2);
      const success = await api.SaveSkinConfig(skinName, json);
      if (success) {
        onSaved(config);
        onClose();
      } else {
        showToast('Erro ao salvar skin.');
      }
    } catch (err) {
      console.error('Save skin error:', err);
      showToast('Erro ao salvar arquivo de skin.');
    } finally {
      setLoading(false);
    }
  };

  const handleApplyPreview = () => {
    onSaved(config);
    showToast('Pré-visualização aplicada!');
  };

  const handleResetDefault = () => {
    setConfig({ ...DEFAULT_CONFIG, name: skinName });
    showToast('Valores restaurados para o padrão.');
  };

  // Helper to compute CSS border value for preview
  const getPreviewBorder = () => {
    const rawColor = config.borderColor || '#ffffff';
    const op = config.borderOpacity ?? 0.25;
    const w = config.borderWidth ?? 1;
    
    let finalColor = rawColor;
    if (rawColor.startsWith('#')) {
      const hex = rawColor.replace('#', '');
      const r = parseInt(hex.substring(0, 2) || 'ff', 16);
      const g = parseInt(hex.substring(2, 4) || 'ff', 16);
      const b = parseInt(hex.substring(4, 6) || 'ff', 16);
      finalColor = `rgba(${r}, ${g}, ${b}, ${op})`;
    } else if (rawColor.startsWith('rgba')) {
      finalColor = rawColor.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, `rgba($1,$2,$3, ${op})`);
    } else if (rawColor.startsWith('hsl')) {
      finalColor = rawColor.replace('hsl', 'hsla').replace(')', `, ${op})`);
    }
    return `${w}px solid ${finalColor}`;
  };

  return (
    <div className="modal-backdrop skin-modal-backdrop">
      <div className="skin-editor-container glass-panel">
        
        {/* Header */}
        <div className="skin-editor-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div className="skin-badge">
              <Sparkles size={18} color="var(--primary)" />
            </div>
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>
                Editor de Skin: <span style={{ color: 'var(--primary)' }}>{skinName}</span>
              </h2>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                Personalize fundo, barras, bordas Gryphlink e cores do sistema
              </span>
            </div>
          </div>
          <button className="btn icon-only" onClick={onClose} title="Fechar">
            <X size={20} />
          </button>
        </div>

        {/* Navigation Sub-Tabs */}
        <div className="skin-nav-tabs">
          <button 
            className={`skin-nav-tab ${activeSubTab === 'background' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('background')}
          >
            <Monitor size={16} />
            Plano de Fundo
          </button>
          <button 
            className={`skin-nav-tab ${activeSubTab === 'bars' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('bars')}
          >
            <Layout size={16} />
            Barras (Lateral & Topo)
          </button>
          <button 
            className={`skin-nav-tab ${activeSubTab === 'borders' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('borders')}
          >
            <Square size={16} />
            Bordas (Gryphlink)
          </button>
          <button 
            className={`skin-nav-tab ${activeSubTab === 'colors' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('colors')}
          >
            <Palette size={16} />
            Cores & Acento
          </button>
        </div>

        {/* Content Body */}
        <div className="skin-editor-body">

          {/* TAB 1: BACKGROUND */}
          {activeSubTab === 'background' && (
            <div className="skin-tab-pane">
              <div className="skin-section-title">
                <Sliders size={16} color="var(--primary)" />
                Tipo de Fundo Principal
              </div>

              {/* Type Switcher */}
              <div className="skin-type-selector">
                <button 
                  type="button"
                  className={`skin-type-btn ${config.backgroundType === 'image' ? 'active' : ''}`}
                  onClick={() => setConfig(prev => ({ ...prev, backgroundType: 'image' }))}
                >
                  <ImageIcon size={18} />
                  Imagem
                </button>
                <button 
                  type="button"
                  className={`skin-type-btn ${config.backgroundType === 'video' ? 'active' : ''}`}
                  onClick={() => setConfig(prev => ({ ...prev, backgroundType: 'video' }))}
                >
                  <Video size={18} />
                  Vídeo (MP4 / WEBM)
                </button>
                <button 
                  type="button"
                  className={`skin-type-btn ${config.backgroundType === 'color' ? 'active' : ''}`}
                  onClick={() => setConfig(prev => ({ ...prev, backgroundType: 'color' }))}
                >
                  <Palette size={18} />
                  Apenas Cor
                </button>
              </div>

              {/* File / URL Input (For Image or Video) */}
              {config.backgroundType !== 'color' && (
                <div className="skin-field-card">
                  <label className="skin-label">
                    {config.backgroundType === 'video' ? 'Origem do Vídeo' : 'Origem da Imagem'}
                  </label>
                  <div style={{ display: 'flex', gap: '10px', marginTop: '6px' }}>
                    <button 
                      type="button"
                      className="btn primary" 
                      onClick={() => handlePickAsset(config.backgroundType as 'image' | 'video', 'backgroundUrl')}
                      style={{ whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                      <FolderOpen size={16} />
                      Escolher do PC
                    </button>
                    <input 
                      type="text" 
                      className="modern-input" 
                      placeholder="Ou cole uma URL (ex: https://... ou http://appassets/...)"
                      value={config.backgroundUrl}
                      onChange={e => setConfig(prev => ({ ...prev, backgroundUrl: e.target.value }))}
                      style={{ flex: 1 }}
                    />
                    {config.backgroundUrl && (
                      <button 
                        type="button"
                        className="btn" 
                        onClick={() => setConfig(prev => ({ ...prev, backgroundUrl: '' }))}
                        title="Limpar fundo"
                      >
                        <X size={16} />
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Opacity & Blur Sliders */}
              <div className="skin-field-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="skin-label">Opacidade do Fundo</label>
                  <span style={{ fontSize: '13px', color: 'var(--primary)', fontWeight: 600 }}>
                    {Math.round((config.backgroundOpacity ?? 1) * 100)}%
                  </span>
                </div>
                <input 
                  type="range" 
                  min="0.05" 
                  max="1.0" 
                  step="0.05"
                  value={config.backgroundOpacity ?? 1}
                  onChange={e => setConfig(prev => ({ ...prev, backgroundOpacity: parseFloat(e.target.value) }))}
                  className="modern-slider"
                />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
                  <label className="skin-label">Desfoque (Blur)</label>
                  <span style={{ fontSize: '13px', color: 'var(--primary)', fontWeight: 600 }}>
                    {config.backgroundBlur ?? 0}px
                  </span>
                </div>
                <input 
                  type="range" 
                  min="0" 
                  max="25" 
                  step="1"
                  value={config.backgroundBlur ?? 0}
                  onChange={e => setConfig(prev => ({ ...prev, backgroundBlur: parseInt(e.target.value, 10) }))}
                  className="modern-slider"
                />
              </div>

              {/* Background Base Color */}
              <div className="skin-field-card">
                <label className="skin-label">Cor Base de Fundo (Camada Inferior)</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px' }}>
                  <input 
                    type="color" 
                    value={config.backgroundColor || '#0f131a'}
                    onChange={e => setConfig(prev => ({ ...prev, backgroundColor: e.target.value }))}
                    style={{ width: '42px', height: '42px', borderRadius: '8px', border: 'none', cursor: 'pointer', background: 'transparent' }}
                  />
                  <input 
                    type="text" 
                    className="modern-input" 
                    value={config.backgroundColor}
                    onChange={e => setConfig(prev => ({ ...prev, backgroundColor: e.target.value }))}
                    style={{ width: '140px' }}
                  />
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    Visível atrás de fundos semitransparentes
                  </span>
                </div>
              </div>

              {/* Live Preview Box */}
              <div className="skin-preview-wrapper">
                <span className="skin-label" style={{ marginBottom: '8px', display: 'block' }}>Prévia do Fundo</span>
                <div 
                  className="skin-mini-preview"
                  style={{
                    backgroundColor: config.backgroundColor,
                    position: 'relative',
                    height: '110px',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    border: '1px solid var(--border)'
                  }}
                >
                  {config.backgroundType === 'video' && config.backgroundUrl ? (
                    <video 
                      src={config.backgroundUrl} 
                      autoPlay 
                      loop 
                      muted 
                      playsInline 
                      style={{
                        position: 'absolute',
                        inset: 0,
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        opacity: config.backgroundOpacity,
                        filter: config.backgroundBlur ? `blur(${config.backgroundBlur}px)` : 'none'
                      }}
                    />
                  ) : config.backgroundUrl && config.backgroundType === 'image' ? (
                    <div 
                      style={{
                        position: 'absolute',
                        inset: 0,
                        backgroundImage: `url('${config.backgroundUrl}')`,
                        backgroundSize: 'cover',
                        backgroundPosition: 'center',
                        opacity: config.backgroundOpacity,
                        filter: config.backgroundBlur ? `blur(${config.backgroundBlur}px)` : 'none'
                      }}
                    />
                  ) : null}
                  <div style={{ position: 'relative', zIndex: 2, padding: '12px', color: '#fff', textShadow: '0 2px 4px rgba(0,0,0,0.8)' }}>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>Exemplo de Conteúdo</div>
                    <div style={{ fontSize: '11px', opacity: 0.8 }}>Texto sobre o plano de fundo configurado</div>
                  </div>
                </div>
              </div>

            </div>
          )}

          {/* TAB 2: BARS (SIDEBAR & TITLEBAR) */}
          {activeSubTab === 'bars' && (
            <div className="skin-tab-pane">
              
              {/* Left Sidebar Customization */}
              <div className="skin-field-card">
                <div className="skin-section-title">
                  <Layout size={16} color="var(--primary)" />
                  Barra Lateral Esquerda (Sidebar)
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                  Personalize a aparência da barra de navegação retrátil
                </p>

                <label className="skin-label">Imagem da Barra Lateral (Opcional)</label>
                <div style={{ display: 'flex', gap: '10px', marginTop: '6px', marginBottom: '16px' }}>
                  <button 
                    type="button"
                    className="btn primary" 
                    onClick={() => handlePickAsset('image', 'sidebarImage')}
                    style={{ whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '8px' }}
                  >
                    <FolderOpen size={16} />
                    Escolher Imagem
                  </button>
                  <input 
                    type="text" 
                    className="modern-input" 
                    placeholder="Cole uma URL de imagem para a sidebar..."
                    value={config.sidebarImage}
                    onChange={e => setConfig(prev => ({ ...prev, sidebarImage: e.target.value }))}
                    style={{ flex: 1 }}
                  />
                  {config.sidebarImage && (
                    <button 
                      type="button"
                      className="btn" 
                      onClick={() => setConfig(prev => ({ ...prev, sidebarImage: '' }))}
                      title="Remover imagem"
                    >
                      <X size={16} />
                    </button>
                  )}
                </div>

                <label className="skin-label">Cor de Vidro / Fundo da Sidebar</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '6px' }}>
                  <input 
                    type="text" 
                    className="modern-input" 
                    value={config.sidebarColor}
                    onChange={e => setConfig(prev => ({ ...prev, sidebarColor: e.target.value }))}
                    style={{ flex: 1 }}
                  />
                  <button 
                    type="button" 
                    className="btn"
                    onClick={() => setConfig(prev => ({ ...prev, sidebarColor: 'hsla(220, 20%, 12%, 0.7)' }))}
                    style={{ fontSize: '12px' }}
                  >
                    Padrão
                  </button>
                </div>
              </div>

              {/* Floating Titlebar Customization */}
              <div className="skin-field-card">
                <div className="skin-section-title">
                  <Monitor size={16} color="var(--primary)" />
                  Barra Superior (Titlebar Flutuante)
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                  Personalize a aparência dos controles de fechar/minimizar no topo
                </p>

                <label className="skin-label">Imagem da Titlebar (Opcional)</label>
                <div style={{ display: 'flex', gap: '10px', marginTop: '6px', marginBottom: '16px' }}>
                  <button 
                    type="button"
                    className="btn primary" 
                    onClick={() => handlePickAsset('image', 'titlebarImage')}
                    style={{ whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '8px' }}
                  >
                    <FolderOpen size={16} />
                    Escolher Imagem
                  </button>
                  <input 
                    type="text" 
                    className="modern-input" 
                    placeholder="Cole uma URL de imagem para a titlebar..."
                    value={config.titlebarImage}
                    onChange={e => setConfig(prev => ({ ...prev, titlebarImage: e.target.value }))}
                    style={{ flex: 1 }}
                  />
                  {config.titlebarImage && (
                    <button 
                      type="button"
                      className="btn" 
                      onClick={() => setConfig(prev => ({ ...prev, titlebarImage: '' }))}
                      title="Remover imagem"
                    >
                      <X size={16} />
                    </button>
                  )}
                </div>

                <label className="skin-label">Cor de Vidro / Fundo da Titlebar</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '6px' }}>
                  <input 
                    type="text" 
                    className="modern-input" 
                    value={config.titlebarColor}
                    onChange={e => setConfig(prev => ({ ...prev, titlebarColor: e.target.value }))}
                    style={{ flex: 1 }}
                  />
                  <button 
                    type="button" 
                    className="btn"
                    onClick={() => setConfig(prev => ({ ...prev, titlebarColor: 'hsla(220, 20%, 12%, 0.7)' }))}
                    style={{ fontSize: '12px' }}
                  >
                    Padrão
                  </button>
                </div>
              </div>

            </div>
          )}

          {/* TAB 3: BORDERS (GRYPHLINK STYLE) */}
          {activeSubTab === 'borders' && (
            <div className="skin-tab-pane">
              <div className="skin-section-title">
                <Square size={16} color="var(--primary)" />
                Bordas e Contornos (Estilo Gryphlink)
              </div>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '14px' }}>
                Configure o contorno arredondado, translúcido e elegante ao redor da janela principal, barra lateral e painéis.
              </p>

              {/* Presets Rápidos */}
              <div className="skin-color-presets">
                {BORDER_PRESETS.map(preset => (
                  <button
                    key={preset.name}
                    type="button"
                    className="skin-preset-pill"
                    onClick={() => setConfig(prev => ({
                      ...prev,
                      borderColor: preset.color,
                      borderOpacity: preset.opacity,
                      borderWidth: preset.width
                    }))}
                  >
                    <span className="preset-swatch" style={{ backgroundColor: preset.color }} />
                    <span>{preset.name}</span>
                  </button>
                ))}
              </div>

              {/* Border Color */}
              <div className="skin-field-card" style={{ marginTop: '14px' }}>
                <label className="skin-label">Cor da Borda</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px' }}>
                  <input 
                    type="color" 
                    value={config.borderColor?.startsWith('#') ? config.borderColor : '#ffffff'}
                    onChange={e => setConfig(prev => ({ ...prev, borderColor: e.target.value }))}
                    style={{ width: '42px', height: '42px', borderRadius: '8px', border: 'none', cursor: 'pointer', background: 'transparent' }}
                  />
                  <input 
                    type="text" 
                    className="modern-input" 
                    value={config.borderColor || '#ffffff'}
                    onChange={e => setConfig(prev => ({ ...prev, borderColor: e.target.value }))}
                    style={{ flex: 1 }}
                  />
                  <button 
                    type="button" 
                    className="btn"
                    onClick={() => setConfig(prev => ({ ...prev, borderColor: '#ffffff' }))}
                    style={{ fontSize: '12px' }}
                  >
                    Branco
                  </button>
                </div>
              </div>

              {/* Border Opacity & Width */}
              <div className="skin-field-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="skin-label">Opacidade da Borda (Transparência)</label>
                  <span style={{ fontSize: '13px', color: 'var(--primary)', fontWeight: 600 }}>
                    {Math.round((config.borderOpacity ?? 0.25) * 100)}%
                  </span>
                </div>
                <input 
                  type="range" 
                  min="0.05" 
                  max="1.0" 
                  step="0.05"
                  value={config.borderOpacity ?? 0.25}
                  onChange={e => setConfig(prev => ({ ...prev, borderOpacity: parseFloat(e.target.value) }))}
                  className="modern-slider"
                />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
                  <label className="skin-label">Espessura da Borda</label>
                  <span style={{ fontSize: '13px', color: 'var(--primary)', fontWeight: 600 }}>
                    {config.borderWidth ?? 1}px
                  </span>
                </div>
                <input 
                  type="range" 
                  min="1" 
                  max="4" 
                  step="1"
                  value={config.borderWidth ?? 1}
                  onChange={e => setConfig(prev => ({ ...prev, borderWidth: parseInt(e.target.value, 10) }))}
                  className="modern-slider"
                />
              </div>

              {/* Live Preview Card */}
              <div className="skin-field-card">
                <label className="skin-label" style={{ marginBottom: '10px', display: 'block' }}>Prévia do Contorno</label>
                <div 
                  style={{
                    padding: '24px',
                    borderRadius: '20px',
                    background: 'rgba(20, 24, 33, 0.85)',
                    backdropFilter: 'blur(16px)',
                    border: getPreviewBorder(),
                    boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: '#fff' }}>Estilo de Borda Gryphlink</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Observe o contorno suave e translúcido ao redor deste card</div>
                  </div>
                  <span style={{ fontSize: '12px', padding: '6px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: getPreviewBorder() }}>
                    {config.borderWidth ?? 1}px / {Math.round((config.borderOpacity ?? 0.25) * 100)}%
                  </span>
                </div>
              </div>

            </div>
          )}

          {/* TAB 4: COLORS & ACCENTS */}
          {activeSubTab === 'colors' && (
            <div className="skin-tab-pane">
              <div className="skin-section-title">
                <Palette size={16} color="var(--primary)" />
                Paletas Rápidas Pré-Configuradas
              </div>

              <div className="skin-color-presets">
                {COLOR_PRESETS.map(preset => {
                  const isSelected = config.primaryColor === preset.color;
                  return (
                    <button
                      key={preset.name}
                      type="button"
                      className={`skin-preset-pill ${isSelected ? 'active' : ''}`}
                      onClick={() => setConfig(prev => ({
                        ...prev,
                        primaryColor: preset.color,
                        primaryHover: preset.hover
                      }))}
                    >
                      <span className="preset-swatch" style={{ backgroundColor: preset.color }} />
                      <span>{preset.name}</span>
                      {isSelected && <Check size={14} color="var(--primary)" />}
                    </button>
                  );
                })}
              </div>

              <div className="skin-field-card" style={{ marginTop: '16px' }}>
                <label className="skin-label">Cor Primária Personalizada</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px' }}>
                  <input 
                    type="color" 
                    value={config.primaryColor.startsWith('#') ? config.primaryColor : '#8A2BE2'}
                    onChange={e => {
                      const hex = e.target.value;
                      setConfig(prev => ({ ...prev, primaryColor: hex, primaryHover: hex }));
                    }}
                    style={{ width: '42px', height: '42px', borderRadius: '8px', border: 'none', cursor: 'pointer', background: 'transparent' }}
                  />
                  <input 
                    type="text" 
                    className="modern-input" 
                    value={config.primaryColor}
                    onChange={e => setConfig(prev => ({ ...prev, primaryColor: e.target.value }))}
                    style={{ flex: 1 }}
                  />
                </div>
              </div>

              <div className="skin-field-card">
                <label className="skin-label">Exemplo de Botões com a Cor Primária</label>
                <div style={{ display: 'flex', gap: '12px', marginTop: '10px' }}>
                  <button 
                    className="btn" 
                    style={{ 
                      backgroundColor: config.primaryColor, 
                      color: '#fff',
                      boxShadow: `0 0 16px ${config.primaryColor}` 
                    }}
                  >
                    Botão de Ação
                  </button>
                  <button 
                    className="btn"
                    style={{
                      border: `1px solid ${config.primaryColor}`,
                      color: config.primaryColor,
                      background: 'transparent'
                    }}
                  >
                    Destaque Secundário
                  </button>
                </div>
              </div>

            </div>
          )}

        </div>

        {/* Status Notification Toast */}
        {statusMsg && (
          <div className="skin-status-banner">
            {statusMsg}
          </div>
        )}

        {/* Footer Actions */}
        <div className="skin-editor-footer">
          <button 
            type="button" 
            className="btn" 
            onClick={handleResetDefault}
            title="Restaurar valores padrão"
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <RotateCcw size={15} />
            Restaurar Padrão
          </button>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button 
              type="button" 
              className="btn" 
              onClick={handleApplyPreview}
            >
              Testar Agora
            </button>
            <button 
              type="button" 
              className="btn primary" 
              onClick={handleSave}
              disabled={loading}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Check size={16} />
              {loading ? 'Salvando...' : 'Salvar e Aplicar'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};

export default SkinEditorModal;
