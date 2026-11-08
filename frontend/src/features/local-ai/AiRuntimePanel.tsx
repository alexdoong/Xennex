import type { AiRuntime, OllamaServer } from './types';

export interface RuntimeActions {
  runtime: AiRuntime | null;
  detectRuntime: () => Promise<unknown>;
  startRuntime: () => Promise<unknown>;
  releaseModel: () => Promise<unknown>;
}
interface Props extends RuntimeActions {
  busy: boolean; locked: boolean; savedEndpoint: string;
  select: (server: OllamaServer, model: string) => void;
}
export default function AiRuntimePanel({ runtime, busy, locked, savedEndpoint, select, detectRuntime, startRuntime, releaseModel }: Props) {
  const canRelease = runtime?.servers.some(server => server.owned && server.endpoint.replace(/\/$/, '') === savedEndpoint.replace(/\/$/, '') && server.models.some(model => model.loaded));
  return <div className="ai-runtime">
    <h4>Motor e modelos no computador</h4>
    <p>Detecte o Ollama ou inicie uma instância para o Xennex. Os modelos precisam estar instalados; nenhum download é iniciado aqui.</p>
    <div className="ai-actions">
      <button className="btn secondary" type="button" disabled={busy} onClick={() => { void detectRuntime(); }}>Detectar Ollama</button>
      <button className="btn secondary" type="button" disabled={busy || locked || runtime?.installed === false} onClick={() => { void startRuntime(); }}>Iniciar Ollama pelo Xennex</button>
      <button className="btn secondary" type="button" disabled={busy || locked || !canRelease} onClick={() => { void releaseModel(); }}>Liberar modelos da memória</button>
    </div>
    {runtime?.modelsDirectory && <small>Modelos desta instalação: {runtime.modelsDirectory}</small>}
    {runtime && !runtime.installed && <p>Instalação padrão do Ollama não encontrada. Você ainda pode conectar um servidor iniciado manualmente.</p>}
    {runtime?.servers.length === 0 && <p>Nenhum servidor Ollama respondeu nos endereços verificados.</p>}
    {runtime?.servers.map(server => <section className="ai-runtime-server" key={server.endpoint}>
      <div><strong>{server.owned ? 'Iniciado pelo Xennex' : 'Servidor externo'}</strong><small>{server.endpoint}</small></div>
      <div className="ai-model-cards">{server.models.map(model => <button className="btn secondary ai-model-card" type="button" key={model.name} disabled={busy || locked} onClick={() => select(server, model.name)}>
        <strong>{model.name}</strong><span>{model.loaded ? 'Carregado na memória' : 'Disponível em disco'} · {model.diskGb.toFixed(1)} GiB em disco</span>
        {model.loaded && <small>{model.loadedVramGb.toFixed(1)} GiB na GPU · contexto {model.loadedContext || 'não informado'}</small>}
        <small>Usar nesta configuração</small>
      </button>)}</div>
      {!server.models.length && <p>O motor está pronto, mas não há modelos locais instalados.</p>}
      <small>Consulta: {new Date(server.capturedAt).toLocaleTimeString()} · “Detectar Ollama” atualiza esta lista.</small>
    </section>)}
    <small>A instância iniciada pelo Xennex usa uma tarefa por vez, desativa a nuvem do Ollama e encerra junto com o app. Servidores externos permanecem sob seu controle.</small>
  </div>;
}
