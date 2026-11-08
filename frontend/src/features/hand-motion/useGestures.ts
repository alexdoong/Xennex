import { useCallback, useEffect, useRef, useState } from 'react';
import type { GestureProfile, GestureStatus } from './types';

export function useGestures() {
  const api = window.chrome?.webview?.hostObjects?.api;
  const [profile, setProfile] = useState<GestureProfile | null>(null);
  const [status, setStatus] = useState<GestureStatus>({ running: false, armed: false, message: 'Câmera desligada.', revision: 0 });
  const [camera, setCamera] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const mounted = useRef(true);
  const revision = useRef(-1);
  const acting = useRef(false);
  const dirtyRef = useRef(false);
  const pollDelay = useRef(500);
  const refresh = useCallback(async () => {
    if (!api) return;
    const next: GestureStatus = JSON.parse(await api.GetGestureStatus());
    if (!mounted.current) return;
    pollDelay.current = next.running ? 40 : 500;
    setStatus(next);
    if (revision.current !== next.revision && !dirtyRef.current) {
      const updated: GestureProfile = JSON.parse(await api.GetGestureConfig());
      if (mounted.current) { setProfile(updated); revision.current = next.revision; }
    }
  }, [api]);
  useEffect(() => {
    mounted.current = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { if (!acting.current) await refresh(); }
      catch (e) { if (mounted.current) setError(String(e)); }
      if (mounted.current) timer = setTimeout(poll, pollDelay.current);
    };
    if (api) {
      void api.GetHandMotionCameraIndex().then(value => { if (mounted.current) setCamera(value); }).catch(e => setError(String(e)));
      void poll();
    }
    return () => { mounted.current = false; clearTimeout(timer); };
  }, [api, refresh]);
  function edit(next: GestureProfile) {
    dirtyRef.current = true; setDirty(true); setProfile(next);
  }
  async function run(operation: () => Promise<unknown>) {
    if (acting.current) return;
    acting.current = true; setBusy(true); setError('');
    try { await operation(); await refresh(); }
    catch (e) { if (mounted.current) setError(String(e)); }
    finally { acting.current = false; if (mounted.current) setBusy(false); }
  }
  async function save() {
    if (!api || !profile) throw new Error('O recurso precisa do aplicativo Windows.');
    await api.SaveGestureConfig(JSON.stringify(profile));
    dirtyRef.current = false; setDirty(false); revision.current = -1;
  }
  return { api, profile, status, camera, setCamera, error, busy, dirty, edit, run, save };
}
