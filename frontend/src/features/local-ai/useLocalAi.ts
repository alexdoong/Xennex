import { useCallback, useEffect, useRef, useState } from 'react';
import type { AiState, AiSettings, AiRuntime, AiSpecialist, AiProjectEdit, AiNote, AiRunRequest } from './types';

function api() {
  const bridge = window.chrome?.webview?.hostObjects?.api;
  if (!bridge) throw Error('A IA local funciona no aplicativo Xennex para Windows.');
  return bridge;
}
export function useLocalAi(active: boolean) {
  const [state, setState] = useState<AiState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [runtime, setRuntime] = useState<AiRuntime | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const polling = useRef(false);
  const refreshSequence = useRef(0);
  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    const next = JSON.parse(await api().GetAiState()) as AiState;
    if (!next || !next.settings || !Array.isArray(next.chats)) throw Error('Esta versão do aplicativo não possui a ponte de IA local. Abra o build atualizado.');
    if (sequence === refreshSequence.current) setState(next);
  }, []);
  useEffect(() => {
    if (!active) return;
    let disposed = false, tick = 0;
    const update = async () => {
      if (polling.current || disposed) return;
      polling.current = true;
      try {
        if (tick++ % 5 === 0) await api().RefreshAiResources();
        if (!disposed) await refresh();
      } catch (e) { if (!disposed) setError(String(e)); }
      finally { polling.current = false; }
    };
    void update(); const timer = window.setInterval(() => { void update(); }, 700);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [active, refresh]);
  const action = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError('');
    try { const result = await fn(); await refresh(); return result; }
    catch (e) { setError(String(e)); return undefined; }
    finally { setBusy(false); }
  };
  return { state, error, busy, models, runtime,
    detectRuntime: () => action(async () => { const found = JSON.parse(await api().DetectAiRuntime()) as AiRuntime; setRuntime(found); setModels([...new Set(found.servers.filter(server=>server.endpoint.replace(/\/$/,'')===state?.settings.endpoint.replace(/\/$/,'')).flatMap(server=>server.models.map(model=>model.name)))]); return found; }),
    startRuntime: () => action(async () => { const found = JSON.parse(await api().StartAiRuntime()) as AiRuntime; setRuntime(found); return found; }),
    releaseModel: () => action(async () => { const found = JSON.parse(await api().ReleaseAiModel()) as AiRuntime; setRuntime(found); return found; }),
    saveSpecialist: (profile: AiSpecialist) => action(() => api().SaveAiSpecialist(JSON.stringify(profile))),
    newProject: (title: string) => action(() => api().CreateAiProject(title)),
    saveProject: (id: string, project: AiProjectEdit) => action(async () => { await api().SaveAiProject(id, JSON.stringify(project)); return true; }),
    saveNote: (id: string, revision: number, note: AiNote) => action(async () => { await api().SaveAiNote(id, revision, JSON.stringify(note)); return true; }),
    exportNotebook: (id: string, specialistId: string) => action(() => api().ExportAiNotebook(id, specialistId)),
    runProject: (id: string, request: AiRunRequest) => action(() => api().RunAiProject(id, JSON.stringify(request))),
    reviewRun: (id: string, runId: string, score: number, interventions: number, review: string) => action(async () => { await api().ReviewAiRun(id, runId, score, interventions, review); return true; }),
    newChat: () => action(() => api().CreateAiChat()),
    remove: (id: string) => action(() => api().DeleteAiChat(id)),
    send: (id: string, text: string) => action(() => api().SendAiMessage(id, text)),
    cancel: (id: string) => action(() => api().CancelAiJob(id)),
    pause: (value: boolean) => action(() => api().PauseAiQueue(value)),
    save: (settings: AiSettings) => action(() => api().SaveAiSettings(JSON.stringify(settings))),
    discover: () => action(async () => { const found = JSON.parse(await api().GetAiModels()) as string[]; setModels(found); return found; }),
  };
}
