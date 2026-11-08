import { useState } from 'react';
import type { AliceEvokedMemory, AliceFrame } from './aliceTypes';

function description(entry: AliceEvokedMemory, frames: AliceFrame[]) {
  const ref = entry.moment_ref;
  const source = ref.source_context;
  const frame = source && frames.find(item => item.stream_id === source.stream_id && item.sequence === source.source_sequence);
  const modalities = ['imagem', 'áudio', 'texto'].filter((_, index) => ref.known[index]).join(' e ');
  if (frame) return `${frame.label} (${modalities})`;
  if (source) return `${modalities}, recebidos em ${new Date(source.captured_wall * 1000).toLocaleString('pt-BR')}`;
  return `${modalities}, aos ${ref.acquired_at.toFixed(1)} segundos da sessão`;
}

export default function AliceEvocation({ entries, frames, available, onFeedback }: {
  entries: AliceEvokedMemory[]; frames: AliceFrame[]; available: boolean;
  onFeedback: (relevance: number) => Promise<boolean>;
}) {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  if (entries.length === 0) return null;
  async function send(relevance: number) {
    setBusy(true);
    try { if (await onFeedback(relevance)) setSent(true); }
    finally { setBusy(false); }
  }
  return <div className="alice-evocation">
    <p>Lembranças relacionadas à conversa:</p>
    <ol>{entries.map((entry, index) => <li key={index}>{description(entry, frames)}</li>)}</ol>
    {available && !sent && <div className="ai-actions" role="group" aria-label="Relevância da primeira lembrança">
      <button type="button" className="btn secondary" disabled={busy} onClick={() => void send(1)}>A primeira tem a ver</button>
      <button type="button" className="btn secondary" disabled={busy} onClick={() => void send(-1)}>A primeira não tem a ver</button>
    </div>}
    {sent && <small>Avaliação enviada.</small>}
    <small>A avaliação orienta a evocação; não corrige os fatos lembrados.</small>
  </div>;
}
