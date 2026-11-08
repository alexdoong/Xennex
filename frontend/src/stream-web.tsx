import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import StreamWorkspace from './features/stream/StreamWorkspace';
import { StreamProvider } from './features/stream/StreamContext';
createRoot(document.getElementById('root')!).render(<StrictMode><StreamProvider><StreamWorkspace standalone initialRoom={new URLSearchParams(location.search).get('room') || ''}/></StreamProvider></StrictMode>);
