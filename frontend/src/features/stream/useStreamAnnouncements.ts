import { useEffect, useState } from 'react';
import type { RoomSnapshot } from './RoomClient';
import { StreamAnnouncements, type NewScreenShare } from './streamAnnouncements';

export function useStreamAnnouncements(state: RoomSnapshot, generation: number) {
  const [tracker] = useState(() => new StreamAnnouncements());
  const [shares, setShares] = useState<NewScreenShare[]>([]);
  useEffect(() => {
    if (state.phase === 'reconnecting') return;
    if (state.phase !== 'connected' || !state.selfId || !state.participants.some(p => p.peerId === state.selfId)) {
      tracker.reset(); setShares(current => current.length ? [] : current); return;
    }
    const next = tracker.update(JSON.stringify([state.room, state.selfId, generation]), state.participants, state.selfId, state.watching);
    setShares(current => current.length === next.length && current.every((v, i) => v.key === next[i].key && v.name === next[i].name && v.title === next[i].title) ? current : next);
  }, [tracker, state.phase, state.room, state.selfId, state.participants, state.watching, generation]);
  return shares;
}
