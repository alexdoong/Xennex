import { useState } from 'react';
import { entryAdvice, entryReport, type EntryDiagnostic } from './entryDiagnostics';

export default function RoomEntryDiagnostic({ entry, phase, alternative }: { entry: EntryDiagnostic | null; phase: string; alternative: boolean }) {
  const [copyState, setCopyState] = useState('');
  if (!entry) return null;
  const report = entryReport(entry, phase, alternative);
  const copy = async () => {
    try { await navigator.clipboard.writeText(report); setCopyState('Diagnóstico copiado.'); }
    catch { setCopyState('Não foi possível copiar automaticamente. Selecione o relatório abaixo.'); }
  };
  return <details className="room-entry-diagnostic" open={phase === 'error' ? true : undefined}>
    <summary>Diagnóstico da entrada · {entry.result === 'failed' ? 'tentativa encerrada' : entry.result === 'connected' ? 'confirmada' : 'em andamento'}</summary>
    <p>{entryAdvice(entry)}</p>
    <button onClick={() => void copy()}>Copiar diagnóstico da entrada</button>
    {copyState && <p role="status">{copyState}</p>}
    <pre tabIndex={0}>{report}</pre>
  </details>;
}
