import { useState } from 'react';
import type { AiSettings } from './types';
import AiRuntimePanel from './AiRuntimePanel';
import type { RuntimeActions } from './AiRuntimePanel';

interface Props extends RuntimeActions { settings: AiSettings; models: string[]; busy: boolean; locked: boolean; save: (s: AiSettings) => Promise<unknown>; discover: () => Promise<unknown> }
export default function AiSettingsPanel({ settings, models, busy, locked, save, discover, runtime, detectRuntime, startRuntime, releaseModel }: Props) {
  const [draft, setDraft] = useState(settings);
  const update = <K extends keyof AiSettings>(key: K, value: AiSettings[K]) => setDraft(old => ({ ...old, [key]: value }));
  return <section className="glass-panel ai-settings">
    <h3>Conexão e orçamento</h3>
    <AiRuntimePanel runtime={runtime} detectRuntime={detectRuntime} startRuntime={startRuntime} releaseModel={releaseModel} busy={busy} locked={locked} savedEndpoint={settings.endpoint} select={(server, model) => setDraft(old => ({ ...old, provider: 'ollama', autoBudget: true, endpoint: server.endpoint, model }))} />
    <p>Selecione um modelo acima e salve abaixo. Motores compatíveis com a API OpenAI, como LM Studio, continuam disponíveis pela configuração manual.</p>
    <form onSubmit={event => { event.preventDefault(); void save(draft); }}>
      <fieldset disabled={busy || locked}>
        <label>Tipo de conexão<select value={draft.provider} onChange={e => { const provider = e.target.value as AiSettings['provider']; setDraft(old => ({ ...old, provider, autoBudget: provider === 'ollama' })); }}><option value="compatible">API compatível — configuração manual</option><option value="ollama">Ollama — controle nativo</option></select></label>
        <label>Endereço local<input value={draft.endpoint} onChange={e => update('endpoint', e.target.value)} placeholder="http://127.0.0.1:1234/v1" required /></label>
        <div className="ai-settings-grid">
          <label>Modelo<input list="ai-models" value={draft.model} onChange={e => update('model', e.target.value)} placeholder="Identificador retornado pelo motor" maxLength={200} /><datalist id="ai-models">{models.map(model => <option key={model} value={model} />)}</datalist></label>
          <label>Saída máxima (tokens)<input type="number" min={128} max={4096} required value={draft.maxOutputTokens} onChange={e => update('maxOutputTokens', Number(e.target.value))} /></label>
          <label>Limite total de memória (%)<input type="number" min={50} max={85} required value={draft.memoryLimitPercent} onChange={e => update('memoryLimitPercent', Number(e.target.value))} /></label>
          <label>Modo de execução<select value={draft.useGpu ? 'gpu' : 'cpu'} onChange={e => update('useGpu', e.target.value === 'gpu')}><option value="gpu">GPU — verifica RAM e VRAM</option><option value="cpu">CPU — verifica somente RAM</option></select></label>
          {draft.provider === 'ollama' && <>
            <label>Orçamento por modelo<select value={draft.autoBudget ? 'auto' : 'manual'} onChange={e => update('autoBudget', e.target.value === 'auto')}><option value="auto">Estimar com os dados do modelo</option><option value="manual">Definir reservas manualmente</option></select></label>
            <label>Contexto (tokens)<input type="number" min={2048} max={16384} step={512} required value={draft.contextTokens} onChange={e => update('contextTokens', Number(e.target.value))} /></label>
            <label>Manter carregado após responder (segundos)<input type="number" min={0} max={300} required value={draft.keepAliveSeconds} onChange={e => update('keepAliveSeconds', Number(e.target.value))} /></label>
          </>}
          {!draft.autoBudget && <><label>Reserva adicional de RAM (GiB)<input type="number" min={0.25} max={256} step={0.25} required value={draft.additionalRamGb} onChange={e => update('additionalRamGb', Number(e.target.value))} /></label>
          <label>Reserva adicional de VRAM (GiB)<input type="number" min={0.25} max={256} step={0.25} required disabled={!draft.useGpu} value={draft.additionalVramGb} onChange={e => update('additionalVramGb', Number(e.target.value))} /></label></>}
        </div>
        <p>{draft.autoBudget ? 'A fila consulta os pesos e o contexto do modelo. Se já estiver carregado com a mesma configuração, reserva apenas uma margem extra. Aumentos observados no uso de memória ajudam a elevar as próximas estimativas.' : 'Defina a memória extra por resposta, incluindo o carregamento se necessário. Pesos já carregados aparecem no uso atual.'} O limite considera todo o PC e não é um bloqueio físico de memória.</p>
        {draft.provider === 'ollama' && <p>Contexto maior precisa de mais memória. Permanência 0 solicita descarregar após cada resposta; alguns segundos permitem reutilizar o modelo entre mensagens.</p>}
        {!draft.useGpu && draft.provider === 'compatible' && <p className="ai-notice">Configure também o motor para CPU. Esta opção não muda onde o servidor executa o modelo.</p>}
        <div className="ai-actions"><button className="btn primary" type="submit">Salvar configuração</button><button className="btn secondary" type="button" onClick={() => { void discover(); }}>Consultar modelos no endereço salvo</button></div>
      </fieldset>
    </form>
    {locked && <p>Conclua ou cancele a fila para alterar a configuração.</p>}
    {models.length > 0 && <p>{models.length} modelo(s) encontrado(s). Selecione o identificador e salve.</p>}
  </section>;
}
