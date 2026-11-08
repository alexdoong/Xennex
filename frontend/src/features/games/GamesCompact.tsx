import { useState } from 'react';
import { Gamepad2, Plus, Maximize2 } from 'lucide-react';
import { useGamesContext } from './GamesContext';
import type { GameSession } from './types';
import type { AppTab } from '../../layout/navigation';

type Props = {
  openFullWindow: (tab?: AppTab) => void;
};

export default function GamesCompact({ openFullWindow }: Props) {
  const { games, busy, error, save } = useGamesContext();
  const [selectedId, setSelectedId] = useState('');
  const [duration, setDuration] = useState('30');
  const [notes, setNotes] = useState('');
  const [statusMsg, setStatusMsg] = useState('');

  const game = games.find(g => g.id === selectedId) ?? games[0];

  const handleAddSession = async () => {
    if (!game || busy) return;
    setStatusMsg('');
    const now = new Date().toISOString();
    const durationNum = Math.min(1440, Math.max(1, Number(duration) || 30));
    const newSession: GameSession = {
      id: crypto.randomUUID(),
      title: 'Sessão Rápida',
      occurredAt: now,
      createdAt: now,
      updatedAt: now,
      patch: '',
      context: '',
      notes: notes.trim(),
      source: 'manual',
      metrics: [
        { name: 'Duração', value: durationNum, unit: 'min' }
      ]
    };
    const updated = {
      ...game,
      sessions: [newSession, ...game.sessions]
    };
    const result = await save(updated);
    if (result) {
      setNotes('');
      setStatusMsg('Sessão registrada!');
      setTimeout(() => setStatusMsg(''), 2500);
    }
  };

  return (
    <div className="compact-module-view compact-games">
      {error && <p role="alert" className="compact-error">{error}</p>}
      {games.length > 0 ? (
        <>
          <label htmlFor="compact-game-select">Jogo ativo</label>
          <select
            id="compact-game-select"
            value={game?.id ?? ''}
            onChange={e => setSelectedId(e.target.value)}
          >
            {games.map(g => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>

          {game && (
            <div className="compact-game-info">
              <div className="compact-game-meta">
                <strong>{game.name}</strong>
                <span>{game.sessions.length} sessões</span>
              </div>

              <div className="compact-quick-session">
                <h3>Registro rápido</h3>
                <div className="compact-fields-row">
                  <label>Minutos
                    <input
                      type="number"
                      min="1"
                      max="1440"
                      value={duration}
                      onChange={e => setDuration(e.target.value)}
                    />
                  </label>
                  <label className="flex-1">Notas
                    <input
                      type="text"
                      placeholder="Conquistas, progresso…"
                      value={notes}
                      onChange={e => setNotes(e.target.value)}
                    />
                  </label>
                </div>
                <button
                  className="btn primary btn-sm w-full"
                  disabled={busy}
                  onClick={() => void handleAddSession()}
                >
                  <Plus size={14} /> Registrar sessão
                </button>
                {statusMsg && <p className="compact-hint">{statusMsg}</p>}
              </div>

              {game.sessions.length > 0 && (
                <div className="compact-recent-sessions">
                  <h4>Recentes</h4>
                  <ul>
                    {game.sessions.slice(0, 3).map(s => {
                      const dur = s.metrics?.find(m => m.unit === 'min' || m.name.toLowerCase().includes('dura'))?.value;
                      return (
                        <li key={s.id}>
                          <span>{new Date(s.occurredAt).toLocaleDateString()}</span>
                          <span>{dur !== undefined ? `${dur} min` : s.title}</span>
                          {s.notes && <small>{s.notes}</small>}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="compact-empty">
          <Gamepad2 size={28} />
          <p>Nenhum jogo cadastrado. Abra a janela completa para criar sua biblioteca.</p>
        </div>
      )}

      <button
        className="compact-expand-link"
        onClick={() => openFullWindow('wuwa-db')}
      >
        <Maximize2 size={13} />
        <span>Abrir biblioteca completa de jogos</span>
      </button>
    </div>
  );
}
