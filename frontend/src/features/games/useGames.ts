import { useCallback, useEffect, useState } from 'react';
import type { GameDocument, GameLibrary } from './types';
import { normalizeGame } from './types';

function api() {
  const bridge = window.chrome?.webview?.hostObjects?.api;
  if (!bridge) throw Error('Abra esta área no aplicativo Xennex para acessar seus registros locais.');
  return bridge;
}
export function useGames() {
  const [library, setLibrary] = useState<GameLibrary>({ games: [], warnings: [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    setBusy(true); setError('');
    try { const next = JSON.parse(await api().GetGameLibrary()) as GameLibrary; setLibrary({ ...next, games: next.games.map(normalizeGame) }); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const save = async (game: GameDocument, importing = false) => {
    setBusy(true); setError('');
    try {
      const json = JSON.stringify(game);
      const result = normalizeGame(JSON.parse(await (importing ? api().ImportGame(json) : api().SaveGame(json))) as GameDocument);
      setLibrary(previous => ({ ...previous,
        games: previous.games.some(g => g.id === result.id) ? previous.games.map(g => g.id === result.id ? result : g) : [...previous.games, result] }));
      return result;
    } catch (e) { setError(String(e)); return null; }
    finally { setBusy(false); }
  };
  return { ...library, busy, error, setError, refresh, save };
}
