import StreamWorkspace from './StreamWorkspace';
import { StreamProvider } from './StreamContext';
export default function StreamViewer() { return <StreamProvider><StreamWorkspace standalone initialRoom={new URLSearchParams(window.location.search).get('room') || ''} /></StreamProvider>; }
