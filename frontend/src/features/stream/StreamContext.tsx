import { createContext, useContext, type ReactNode } from 'react';
import { useRoom } from './useRoom';

type StreamContextType = ReturnType<typeof useRoom>;

const StreamContext = createContext<StreamContextType | null>(null);

export function StreamProvider({ children }: { children: ReactNode }) {
  const value = useRoom();
  return <StreamContext.Provider value={value}>{children}</StreamContext.Provider>;
}

export function useStreamContext() {
  const ctx = useContext(StreamContext);
  if (!ctx) throw new Error('useStreamContext must be used within StreamProvider');
  return ctx;
}
