import { createContext, useContext, useState, type ReactNode } from 'react';
import { useLocalAi } from './useLocalAi';

type LocalAiContextType = ReturnType<typeof useLocalAi> & {
  selected: string; setSelected: React.Dispatch<React.SetStateAction<string>>;
  drafts: Record<string, string>; setDrafts: React.Dispatch<React.SetStateAction<Record<string, string>>>;
};

const LocalAiContext = createContext<LocalAiContextType | null>(null);

export function LocalAiProvider({ active, children }: { active: boolean; children: ReactNode }) {
  const ai = useLocalAi(active);
  const [selected, setSelected] = useState('');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const value = { ...ai, selected, setSelected, drafts, setDrafts };
  return <LocalAiContext.Provider value={value}>{children}</LocalAiContext.Provider>;
}

export function useLocalAiContext() {
  const ctx = useContext(LocalAiContext);
  if (!ctx) throw new Error('useLocalAiContext must be used within LocalAiProvider');
  return ctx;
}
