import type { KeyboardEvent } from 'react';
import { actions, isContinuous, sources } from './types';
import type { GestureBinding, ActionType } from './types';

interface Props {
  gesture: GestureBinding; disabled: boolean; canRecord: boolean;
  change: (gesture: GestureBinding) => void; record: () => void; clear: () => void; remove: () => void;
}
function captureShortcut(event: KeyboardEvent<HTMLInputElement>, change: (value: string) => void) {
  if (event.key === 'Tab') return;
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(event.key)) return;
  const aliases: Record<string, string> = { ' ': 'space', Escape: 'esc', ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
  const key = aliases[event.key] ?? event.key.toLowerCase();
  if (!/^(?:[a-z0-9]|f[1-9]|f1[0-9]|f2[0-4]|left|right|up|down|enter|esc|space|backspace|delete|home|end|pageup|pagedown)$/.test(key)) return;
  event.preventDefault();
  change([event.metaKey && 'win', event.ctrlKey && 'ctrl', event.altKey && 'alt', event.shiftKey && 'shift', key].filter(Boolean).join('+'));
}
export function GestureEditor({ gesture: g, disabled, canRecord, change, record, clear, remove }: Props) {
  const learned = g.source === 'pose' || g.source === 'motion';
  const instant = g.source === 'motion' || g.source.startsWith('swipe_');
  return <fieldset className="gestures-card" disabled={disabled}>
    <div className="gestures-row">
      <label className="gestures-check"><input type="checkbox" checked={g.enabled} onChange={e => change({ ...g, enabled: e.target.checked })} />Habilitado</label>
      <span className="gestures-tag">{sources[g.source]}</span>
      {learned && <button className="btn secondary" type="button" onClick={remove}>Excluir gesto</button>}
    </div>
    <label>Nome<input maxLength={80} value={g.name} onChange={e => change({ ...g, name: e.target.value })} /></label>
    <label>Ação<select value={g.action.type} onChange={e => change({ ...g, action: { type: e.target.value as ActionType, value: g.action.value || 'win+left' } })}>
      {Object.entries(actions).filter(([key]) => !instant || !isContinuous(key as ActionType)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    {g.action.type === 'shortcut' && <div className="gestures-fields">
      <label>Atalho (texto)<input placeholder="win+left" value={g.action.value} onChange={e => change({ ...g, action: { ...g.action, value: e.target.value.toLowerCase().replace(/\s/g, '') } })} /></label>
      <label>Ou pressione uma combinação<input placeholder="Clique aqui e pressione" value="" onChange={() => {}} onKeyDown={e => captureShortcut(e, value => change({ ...g, action: { ...g.action, value } }))} /></label>
    </div>}
    <details><summary>Ajustar reconhecimento</summary><div className="gestures-fields">
      {!instant && <label>Tempo para confirmar (ms)<input type="number" min="100" max="2000" step="50" value={g.holdMs} onChange={e => change({ ...g, holdMs: Number(e.target.value) })} /></label>}
      {!isContinuous(g.action.type) && <label>Intervalo entre ações (ms)<input type="number" min="250" max="5000" step="50" value={g.cooldownMs} onChange={e => change({ ...g, cooldownMs: Number(e.target.value) })} /></label>}
      {learned && <label>Tolerância: {g.threshold.toFixed(2)}<input type="range" min=".05" max=".5" step=".01" value={g.threshold} onChange={e => change({ ...g, threshold: Number(e.target.value) })} /><small>Menor = mais exigente; maior pode confundir gestos.</small></label>}
    </div></details>
    {learned && <div className="gestures-samples">
      <p>{g.samples.length}/8 amostras · {g.source === 'pose' ? 'Mantenha a pose por 1 segundo.' : 'Faça o movimento em 2 segundos.'}</p>
      <button className="btn secondary" type="button" disabled={!canRecord || g.samples.length >= 8} onClick={record}>Gravar amostra</button>
      <button className="btn secondary" type="button" disabled={!g.samples.length} onClick={clear}>Limpar amostras</button>
      {g.samples.some(s => s.legacy) && <p>Importado do sistema antigo. Confira a ação e teste antes de habilitar.</p>}
    </div>}
  </fieldset>;
}
