import { LayoutDashboard, Database, Cloud, Hand, Settings, Tv, Bot, Images } from 'lucide-react';

export const APP_TABS = [
  { id: 'dashboard', title: 'Dashboard', icon: LayoutDashboard },
  { id: 'wuwa-db', title: 'Jogos', icon: Database },
  { id: 'assets', title: 'Biblioteca', icon: Images },
  { id: 'local-ai', title: 'IA local', icon: Bot },
  { id: 'cloud', title: 'Cloud', icon: Cloud },
  { id: 'stream', title: 'Compartilhamento de Tela & Streams', icon: Tv },
  { id: 'hand-motion', title: 'Gestures', icon: Hand },
  { id: 'settings', title: 'Config', icon: Settings },
] as const;

export type AppTab = typeof APP_TABS[number]['id'];
export const CUSTOMIZABLE_TABS = APP_TABS.filter(tab => tab.id !== 'settings');
