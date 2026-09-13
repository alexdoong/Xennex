import AppShell from './layout/AppShell';
import StreamViewer from './features/stream/StreamViewer';

export default function App() {
  const viewerMode = new URLSearchParams(window.location.search).get('mode') === 'viewer';
  return viewerMode ? <StreamViewer /> : <AppShell />;
}
