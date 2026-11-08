import AppShell from './layout/AppShell';
import StreamViewer from './features/stream/StreamViewer';
import { GamesProvider } from './features/games/GamesContext';
import { StreamProvider } from './features/stream/StreamContext';
import { GesturesProvider } from './features/hand-motion/GesturesContext';
import { LocalAiProvider } from './features/local-ai/LocalAiContext';

export default function App() {
  const viewerMode = new URLSearchParams(window.location.search).get('mode') === 'viewer';
  if (viewerMode) return <StreamViewer />;

  return (
    <GamesProvider>
      <StreamProvider>
        <GesturesProvider>
          <LocalAiProvider active={true}>
            <AppShell />
          </LocalAiProvider>
        </GesturesProvider>
      </StreamProvider>
    </GamesProvider>
  );
}
