import { createContext, useContext, type ReactNode } from 'react';
import { useGestures } from './useGestures';

type GesturesContextType = ReturnType<typeof useGestures>;

const GesturesContext = createContext<GesturesContextType | null>(null);

export function GesturesProvider({ children }: { children: ReactNode }) {
  const value = useGestures();
  return <GesturesContext.Provider value={value}>{children}</GesturesContext.Provider>;
}

export function useGesturesContext() {
  const ctx = useContext(GesturesContext);
  if (!ctx) throw new Error('useGesturesContext must be used within GesturesProvider');
  return ctx;
}
