import React from 'react';
import { Power, Minimize2 } from 'lucide-react';

interface CloseConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onMinimizeToTray: () => void;
  onExit: () => void;
}

const CloseConfirmModal: React.FC<CloseConfirmModalProps> = ({
  isOpen,
  onClose,
  onMinimizeToTray,
  onExit
}) => {
  if (!isOpen) return null;

  return (
    <div className="close-modal-overlay">
      <div className="close-modal-card">
        <div className="close-modal-header">
          <div className="close-icon-badge">
            <Power size={22} color="var(--primary)" />
          </div>
          <div className="close-title-group">
            <h3>Fechar Xennex</h3>
            <p>O que deseja fazer ao fechar o aplicativo?</p>
          </div>
        </div>

        <div className="close-modal-actions">
          <button 
            className="close-choice-btn tray"
            onClick={onMinimizeToTray}
          >
            <div className="choice-icon">
              <Minimize2 size={22} />
            </div>
            <div className="choice-text">
              <strong>Minimizar para a Bandeja (System Tray)</strong>
              <span>O app continuará rodando em segundo plano perto do relógio do Windows</span>
            </div>
          </button>

          <button 
            className="close-choice-btn exit"
            onClick={onExit}
          >
            <div className="choice-icon">
              <Power size={22} />
            </div>
            <div className="choice-text">
              <strong>Fechar o Aplicativo Completamente</strong>
              <span>Encerra todos os processos e serviços em execução</span>
            </div>
          </button>
        </div>

        <div className="close-modal-footer">
          <button 
            className="btn-cancel-close"
            onClick={onClose}
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
};

export default CloseConfirmModal;
