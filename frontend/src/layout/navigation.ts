import { LayoutDashboard, Database, Cloud, Hand, Settings, Tv } from 'lucide-react';

export const APP_TABS = [
  { id: 'dashboard', title: 'Dashboard', icon: LayoutDashboard },
  { id: 'wuwa-db', title: 'WuWa Database', icon: Database },
  { id: 'cloud', title: 'Cloud', icon: Cloud },
  { id: 'stream', title: 'Compartilhamento de Tela & Streams', icon: Tv },
  { id: 'hand-motion', title: 'Hand Motion', icon: Hand },
  { id: 'settings', title: 'Config', icon: Settings },
] as const;

export type AppTab = typeof APP_TABS[number]['id'];
