import StreamWorkspace from './StreamWorkspace';
export default function StreamViewer() { return <StreamWorkspace standalone initialRoom={new URLSearchParams(window.location.search).get('room') || ''} />; }
