import { useEffect, useState } from 'react';
import useAlicePanel from './useAlicePanel';
import AliceEvocation from './AliceEvocation';
import { aliceStatus } from './aliceTypes';
import type { AliceAction, AliceFrame, AliceModality, AliceSettings } from './aliceTypes';

const actionLabels: [AliceAction, string][] = [['name', 'Ensinar um nome'], ['relate', 'Ensinar sobre a experiência'],
  ['correct', 'Corrigir um relato'], ['recall', 'Perguntar sobre um relato'], ['reply', 'Responder à dúvida sobre um nome'],
  ['meaning', 'Consultar uma associação'], ['ask', 'Consultar uma expectativa'], ['feedback', 'Avaliar uma escolha de atenção'], ['talk', 'Conversar · experimental']];
const modalityLabels: [AliceModality, string][] = [['image', 'Imagem PNG'], ['audio', 'Áudio WAV'], ['text', 'Texto UTF-8']];
const visualDetectionLabels = {
  detected: 'Mirage encontrou recortes na última imagem.',
  no_useful_box: 'Mirage não encontrou um recorte útil na última imagem.',
  detector_error: 'Mirage indisponível na última imagem.',
};
const pronunciationLabels = {
  learned: 'Pronúncia registrada',
  heard: 'Palavra reconhecida',
  ambiguous: 'Mais de uma palavra possível',
  unmatched: 'Nenhuma palavra reconhecida',
  unusable_audio: 'O WAV não gerou um padrão utilizável',
  unattended: 'A Alice não atendeu esse áudio',
  duplicate: 'Esse exemplo já está registrado',
  conflicting_example: 'Esse mesmo áudio já está vinculado a outra palavra',
};

export default function AlicePanel({ active }: { active: boolean }) {
  const alice = useAlicePanel(active);
  const [settings, setSettings] = useState<AliceSettings | null>(null);
  const [action, setAction] = useState<AliceAction>('name');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [frames, setFrames] = useState<AliceFrame[]>([]);
  const [frameKey, setFrameKey] = useState('');
  const [pairFocus, setPairFocus] = useState<'image' | 'audio'>('image');
  const [writtenWord, setWrittenWord] = useState('');
  const [lastWordSequence, setLastWordSequence] = useState<number | null>(null);
  const [parentId, setParentId] = useState('');
  const [attentionId, setAttentionId] = useState('');
  const [notice, setNotice] = useState('');
  const [talkInput, setTalkInput] = useState<{ text: string; frame: AliceFrame } | null>(null);
  const state = alice.state;
  useEffect(() => { if (state && !settings) setSettings(state.settings); }, [state, settings]);
  const records = state?.snapshot?.interaction_state?.records ?? [];
  const reports = records.filter(item => item.status === 'completed' && ['relate', 'correct', 'report'].includes(item.request.action));
  const questions = records.filter(item => item.status === 'awaiting_reply');
  const parents = action === 'reply' ? questions : reports;
  const parent = parents.find(item => item.request.id === parentId);
  const frame = frames.find(item => item.stream_id + ':' + item.sequence === frameKey);
  const needsFrame = action === 'name' || action === 'relate';
  const needsParent = ['correct', 'recall', 'reply'].includes(action);
  const attentionActions = state?.currentSnapshot ? state.snapshot?.native_state?.attention_actions ?? [] : [];
  const recallActions = state?.currentSnapshot ? state.snapshot?.native_state?.recall_feedback_actions ?? [] : [];
  const visualDetection = state?.snapshot?.native_state?.last_visual_detection;
  const soundAssociation = state?.snapshot?.native_state?.last_sound_association;
  const pronunciation = state?.snapshot?.native_state?.last_pronunciation;
  const pronunciationReady = pronunciation && (lastWordSequence === null || pronunciation.source_sequence >= lastWordSequence);
  const choice = attentionActions.find(item => String(item.id) === attentionId);
  async function recallFeedback(about: string, relevance: number) {
    try { await alice.send('recall_feedback', { about, relevance }); setNotice('Avaliação da lembrança enviada.'); return true; }
    catch (error) { setNotice(String(error)); return false; }
  }
  const needsAttention = action === 'feedback';
  const draftKey = action + ':' + (needsParent || action === 'talk' ? parentId : needsFrame ? frameKey : needsAttention ? attentionId : 'query');
  const text = drafts[draftKey] ?? '';
  const change = <K extends keyof AliceSettings>(key: K, value: AliceSettings[K]) => setSettings(old => old ? { ...old, [key]: value } : old);
  const select = async (key: 'python' | 'checkpoint' | 'perceptionPython' | 'perceptionModels' | 'mirageModels', kind: string) => {
    const path = await alice.pick(kind); if (path) change(key, path);
  };
  const registerFrame = (added: AliceFrame | null) => {
    if (!added) return;
    setFrames(old => [...old.slice(-31), added]); setFrameKey(added.stream_id + ':' + added.sequence);
    setPairFocus('image');
    setNotice('Arquivo enviado. O nome só será associado se a percepção for concluída.');
  };
  const perceive = async (modality: AliceModality) => {
    const path = await alice.pick(modality);
    if (path) registerFrame(await alice.perceive(modality, path));
  };
  const perceivePair = async () => {
    const image = await alice.pick('image'); if (!image) return;
    const audio = await alice.pick('audio'); if (!audio) return;
    registerFrame(await alice.perceivePair(image, audio));
  };
  const perceiveWord = async (word: string) => {
    const path = await alice.pick('audio');
    if (!path) return;
    const frame = await alice.perceiveWordAudio(path, word);
    if (!frame) return;
    registerFrame(frame);
    setLastWordSequence(frame.sequence);
    if (word) setWrittenWord('');
    setNotice('WAV enviado para prática de palavras.');
  };
  const send = async () => {
    let received = talkInput?.text === text ? talkInput.frame : null;
    if (action === 'talk' && !received) {
      received = await alice.perceiveText(text);
      if (!received) return;
      setTalkInput({ text, frame: received });
    }
    const reference = frame ? { stream_id: frame.stream_id, sequence: frame.sequence } : null;
    const payload = action === 'name' ? { text, focus: frame?.modality === 'image_audio' ? pairFocus : null, moment: null, frame: reference }
      : action === 'relate' ? { text, moment: null, frame: reference }
      : action === 'correct' ? { text, reply_to: parentId }
      : action === 'reply' ? { word: text, reply_to: parentId, focus: null }
      : action === 'feedback' ? { text, action: Number(attentionId) }
      : action === 'talk' ? { text, frame: received ? { stream_id: received.stream_id, sequence: received.sequence } : null, about: parent?.request.id ?? null }
      : action === 'recall' ? { text, about: parentId } : { text };
    const result = await alice.send(action, payload);
    if (result) { setTalkInput(null); setDrafts(old => ({ ...old, [draftKey]: old[draftKey] === text ? '' : old[draftKey] })); setNotice('Mensagem recebida na fila. Acompanhe o resultado abaixo.'); }
  };
  return <section className="glass-panel alice-panel" aria-label="Alice experimental">
    <header><h3>Alice experimental</h3><p>Experiências selecionadas, ensino e memória entre sessões. Diálogo experimental com módulo pré-treinado; sentidos ao vivo ainda estão em desenvolvimento.</p></header>
    <p role="status">{state?.running ? 'Processo ativo' : 'Processo parado'}{state?.running && !state.currentSnapshot ? ' · aguardando o estado desta execução' : ''}</p>
    {state && !state.scriptsAvailable && <p className="ai-error">Os scripts da Alice não estão neste build.</p>}
    {(alice.error || state?.lastError) && <p role="alert" className="ai-error">{alice.error || state?.lastError}</p>}
    {state?.exitCode != null && state.exitCode !== 0 && <p role="alert" className="ai-error">A execução terminou com erro ({state.exitCode}). Os detalhes estão no stderr.log da sessão: {state.directory}</p>}
    {!settings && !alice.error && <p>Carregando a sessão…</p>}
    {settings && <>
      <details open={!state?.running}><summary>Configurar a sessão</summary>
        <fieldset disabled={alice.busy || state?.running}>
          {([['python', 'Python da Alice', 'python'], ['checkpoint', 'Estado inicial existente', 'checkpoint'],
            ['perceptionPython', 'Python da percepção (opcional)', 'python'], ['perceptionModels', 'Pasta do encoder (opcional)', 'models'],
            ['mirageModels', 'Pasta do Mirage para recortes automáticos (opcional)', 'models']] as const).map(([key, label, kind]) =>
            <div className="alice-path" key={key}><label>{label}<input value={settings[key] ?? ''} onChange={e => change(key, e.target.value)} /></label><button type="button" className="btn secondary" onClick={() => void select(key, kind)}>Selecionar {label.toLocaleLowerCase()}</button></div>)}
          <p>O estado inicial é copiado na primeira execução. Retomar usa a memória salva da sessão; não importa novamente o arquivo de origem.</p>
          <div className="alice-settings-grid"><label>Endereço local do Ollama<input value={settings.endpoint} onChange={e => change('endpoint', e.target.value)} /></label>
            <label>Modelo instalado<input value={settings.model} onChange={e => change('model', e.target.value)} /></label>
            <label>Modelo de conversa (opcional)<input value={settings.dialogueModel ?? ''} placeholder="Mesmo modelo instalado" onChange={e => change('dialogueModel', e.target.value)} /></label>
            <label>Atenção na percepção<select aria-label="Atenção na percepção" value={settings.attention ?? 'full'} onChange={e => change('attention', e.target.value as AliceSettings['attention'])}><option value="full">Adquirir todas as modalidades enviadas</option><option value="learned">Atenção aprendida · experimental</option><option value="quiet">Não adquirir os sinais enviados</option></select></label>
            <label>Evocação de lembranças (experimental)<select aria-label="Evocação de lembranças (experimental)" value={settings.memoryRecall ?? 'preserve'} onChange={e => change('memoryRecall', e.target.value as AliceSettings['memoryRecall'])}><option value="preserve">Manter o estado salvo</option><option value="enabled">Ativar evocação durante a interação</option><option value="disabled">Desativar evocação automática</option></select></label>
            <label>Duração em segundos (0 = até parar)<input type="number" min={0} max={3600} value={settings.seconds} onChange={e => change('seconds', Number(e.target.value))} /></label>
            <label>Limite de uso total de RAM<select aria-label="Limite de uso total de RAM" value={settings.ramFraction} onChange={e => change('ramFraction', Number(e.target.value))}><option value={.75}>75%</option><option value={.9}>90% · teste com duração limitada</option></select></label></div>
          <p>Configure primeiro o motor local em “Conexão e orçamento”. Nenhum modelo é baixado por este painel.</p>
          <p>O modelo de conversa gera a fala; o modelo acima interpreta ensinamentos. Deixe vazio para usar o mesmo nos dois. Uma mudança vale para novas mensagens; as pendentes conservam o modelo com que foram recebidas.</p>
        </fieldset>
      </details>
      <div className="ai-actions"><button className="btn primary" disabled={alice.busy || state?.running || !state?.scriptsAvailable} onClick={() => void alice.start(settings)}>Iniciar Alice</button>
        <button className="btn secondary" disabled={alice.busy || !state?.running} onClick={() => void alice.stop()}>Parar e salvar Alice</button></div>
      <details><summary>Estado salvo da memória</summary><p>{state?.currentSnapshot ? 'Relatório desta execução.' : 'Último relatório disponível; não indica que a Alice está ativa.'}</p>
        <p>{state?.snapshot?.ticks ?? 0} passos · {state?.snapshot?.writer_commits ?? 0} gravações nesta execução</p>
        {state?.snapshot?.native_state?.visual_region_moments != null && <p>{state.snapshot.native_state.visual_region_moments} momentos com recortes visuais retidos</p>}
        {visualDetection && <p>{visualDetectionLabels[visualDetection.status]} {visualDetection.count} recortes retidos dessa imagem.</p>}
        {soundAssociation && <p>O último áudio evocou “{soundAssociation.name}” a partir de {soundAssociation.count} {soundAssociation.count === 1 ? 'lembrança audiovisual' : 'lembranças audiovisuais'}.</p>}
        {state?.snapshot?.native_state && <p>{state.snapshot.native_state.observations ?? 0} percepções · {state.snapshot.native_state.moments ?? 0} momentos retidos · {state.snapshot.native_state.forgotten_moments ?? 0} momentos sem episódio disponível · {state.snapshot.native_state.interpretation_versions ?? 0} versões de relatos · {state.snapshot.native_state.attention_feedbacks ?? 0} avaliações de atenção aprendidas</p>}<small>Pasta da sessão: {state?.directory}</small>
      </details>
      <fieldset disabled={alice.busy || !state?.running}><legend>Experiências e ensino</legend>
        <div className="ai-actions">{modalityLabels.map(([modality, label]) => <button className="btn secondary" key={modality} disabled={!state?.settings.perceptionPython} onClick={() => void perceive(modality)}>Enviar {label.toLocaleLowerCase()}</button>)}
          <button className="btn secondary" disabled={!state?.settings.perceptionPython} onClick={() => void perceivePair()}>Enviar imagem e áudio juntos</button></div>
        <details><summary>Palavras faladas · experimental</summary>
          <p>Use um WAV com uma única palavra. Para ensinar outra voz, envie outro exemplo da mesma palavra.</p>
          <label>Palavra escrita<input value={writtenWord} maxLength={72} onChange={e => setWrittenWord(e.target.value)} /></label>
          <div className="ai-actions">
            <button className="btn secondary" disabled={!state?.settings.perceptionPython || !writtenWord.trim()} onClick={() => void perceiveWord(writtenWord.trim())}>Ensinar pronúncia</button>
            <button className="btn secondary" disabled={!state?.settings.perceptionPython} onClick={() => void perceiveWord('')}>Tentar reconhecer palavra</button>
          </div>
          {pronunciationReady && <p role="status">{pronunciationLabels[pronunciation.status]}{pronunciation.word ? ` · “${pronunciation.word}”` : ''}.</p>}
          {state?.snapshot?.native_state?.pronunciation_examples != null && <small>{state.snapshot.native_state.pronunciation_examples} exemplos retidos.</small>}
        </details>
        <label>O que deseja fazer?<select aria-label="O que deseja fazer?" value={action} onChange={e => { setAction(e.target.value as AliceAction); setNotice(''); }}>{actionLabels.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {needsFrame && <label>Experiência selecionada<select aria-label="Experiência selecionada" value={frameKey} onChange={e => { setFrameKey(e.target.value); setPairFocus('image'); }}><option value="">Selecione uma experiência enviada</option>{frames.map(item => <option key={item.stream_id + ':' + item.sequence} value={item.stream_id + ':' + item.sequence}>{item.label} · {item.modality === 'image_audio' ? 'imagem e áudio' : item.modality}</option>)}</select></label>}
        {action === 'name' && frame?.modality === 'image_audio' && <label>A que se refere o nome?<select aria-label="A que se refere o nome?" value={pairFocus} onChange={e => setPairFocus(e.target.value === 'audio' ? 'audio' : 'image')}><option value="image">Imagem</option><option value="audio">Áudio</option></select></label>}
        {needsParent && <label>{action === 'reply' ? 'Dúvida a responder' : 'Relato a consultar ou corrigir'}<select aria-label={action === 'reply' ? 'Dúvida a responder' : 'Relato a consultar ou corrigir'} value={parentId} onChange={e => setParentId(e.target.value)}><option value="">Selecione uma mensagem</option>{parents.map(item => <option value={item.request.id} key={item.request.id}>{item.request.payload.text}</option>)}</select></label>}
        {parent?.result?.question && <p>{parent.result.question}</p>}
        {action === 'talk' && <><label>Assunto da memória (opcional)<select aria-label="Assunto da memória (opcional)" value={parentId} onChange={e => setParentId(e.target.value)}><option value="">Conversa sem um relato selecionado</option>{reports.map(item => <option key={item.request.id} value={item.request.id}>{item.request.payload.text}</option>)}</select></label><p>Sua mensagem será recebida também como texto sensorial. A resposta pode usar conhecimento pré-treinado; falas geradas não são gravadas automaticamente como fatos aprendidos.</p></>}
        {needsAttention && <><label>Escolha recente de atenção<select aria-label="Escolha recente de atenção" value={attentionId} onChange={e => setAttentionId(e.target.value)}><option value="">Selecione uma escolha</option>{attentionActions.map(item => {
          const selected = frames.find(source => source.stream_id === item.frame?.stream_id && source.sequence === item.frame?.sequence);
          const label = { image: 'Imagem', audio: 'Áudio', text: 'Texto', all: 'Todas as modalidades', quiet: 'Sem adquirir o sinal' }[item.action];
          return <option key={item.id} value={item.id}>{selected?.label ?? 'Experiência recente'} · {label} · há {Math.floor(item.age_seconds)}s</option>;
        })}</select></label><p>Feedback sobre uma decisão de atenção aprendida nos últimos 60 segundos. Aprovar uma escolha quieta também é válido. Isso não transforma sua avaliação em um fato sobre o mundo.</p>{attentionActions.length === 0 && <p>Nenhuma escolha disponível. Use atenção aprendida na sessão para avaliar decisões recentes.</p>}</>}
        <form onSubmit={e => { e.preventDefault(); void send(); }}><label>Mensagem para a Alice<textarea aria-label="Mensagem para a Alice" rows={3} maxLength={4096} value={text} onChange={e => setDrafts(old => ({ ...old, [draftKey]: e.target.value }))}
          placeholder={action === 'reply' ? 'Uma palavra, por exemplo: Hami' : action === 'feedback' ? 'Gostei disso. / Não gostei disso.' : action === 'name' ? 'Essa imagem se chama Hami.' : action === 'relate' ? 'O autor dessa imagem é meu pai.' : action === 'correct' ? 'Corrigindo: é minha mãe.' : action === 'recall' ? 'Quem era antes? / E agora? / O que mudou?' : 'Escreva uma pergunta sobre o que foi aprendido.'} /></label>
          <button className="btn primary" disabled={!text.trim() || needsFrame && !frame || needsParent && !parent || needsAttention && !choice || action === 'talk' && !state?.settings.perceptionPython}>Enviar para Alice</button></form>
      </fieldset>
      {notice && <p role="status">{notice}</p>}
      <div className="alice-results" aria-label="Resultados da Alice">{records.map(item => <article className="ai-message" key={item.request.id}>
        <strong>{item.request.action === 'recall_feedback' ? 'Avaliação da relevância de uma lembrança' : item.request.payload.text ?? item.request.payload.word}</strong><small>{aliceStatus[item.status] ?? item.status}</small>
        {item.result?.question && <p>{item.result.question}</p>}{item.result?.error && <p role="alert">{item.result.error}</p>}
        {item.result?.learning?.learned && <p>{item.result.learning.kind === 'recollection_relevance' ? 'Preferência de evocação atualizada.' : 'Aprendizado registrado.'}</p>}
        {item.result?.data?.memory_text && (item.published ?? 0) >= (item.revision ?? 1) && <p>Memória no contexto: {item.result.data.memory_text}</p>}
        {item.result?.data?.proposal?.text && (item.published ?? 0) >= (item.revision ?? 1) && <><p>{item.result.data.proposal.text}</p>{item.result.data.proposal.kind === 'generated_dialogue' && <small>Expressão gerada pelo módulo de linguagem</small>}</>}
        {item.result?.data?.evidence?.association?.evocation && (item.published ?? 0) >= (item.revision ?? 1) && <AliceEvocation entries={item.result.data.evidence.association.evocation.entries} frames={frames} available={!!state?.running && !alice.busy && recallActions.some(choice => choice.about === item.request.id)} onFeedback={value => recallFeedback(item.request.id, value)} />}
        {item.result?.data && <details><summary>Evidência da consulta</summary><pre>{JSON.stringify(item.result.data, null, 2)}</pre></details>}
      </article>)}{records.length === 0 && <p>Os resultados de ensino e consulta aparecerão aqui.</p>}</div>
    </>}
  </section>;
}
