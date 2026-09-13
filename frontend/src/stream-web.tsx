import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import StreamWorkspace from './features/stream/StreamWorkspace';
createRoot(document.getElementById('root')!).render(<StrictMode><StreamWorkspace standalone initialRoom={new URLSearchParams(location.search).get('room') || ''}/></StrictMode>);
