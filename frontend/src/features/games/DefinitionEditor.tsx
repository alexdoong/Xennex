import { useEffect, useState } from 'react';
import { Brain, Settings2, Target, Workflow, Tags, Plus } from 'lucide-react';
import type { GameDefinition, NamedDefinition } from './definitionTypes';
import { gameTypes, metricDefinition, namedDefinition } from './definitionTypes';

function CatalogEditor({ title, hint, items, label, disabled, onChange }: {
  title: string; hint: string; items: NamedDefinition[]; label: string; disabled: boolean; onChange: (items: NamedDefinition[]) => void
}) {
  return <section className="games-definition-section"><div className="games-toolbar"><h3>{title}</h3><button type="button" className="btn secondary" disabled={disabled || items.length >= 100} onClick={() => onChange([...items, namedDefinition()])}><Plus size={14} />Adicionar {label}</button></div><p className="games-muted">{hint}</p>
    <div className="games-definition-grid">{items.map((item, i) => <div className={'games-definition-item ' + (item.archived ? 'is-archived' : '')} key={item.id}>
      <label>Nome de {label} {i + 1}<input required maxLength={80} value={item.name} onChange={e => onChange(items.map(x => x.id === item.id ? { ...x, name: e.target.value } : x))} /></label>
      <label>Descrição de {label} {i + 1}<input maxLength={2000} value={item.description} onChange={e => onChange(items.map(x => x.id === item.id ? { ...x, description: e.target.value } : x))} placeholder="O que significa e como observar?" /></label>
      <button type="button" className="btn secondary" onClick={() => onChange(items.map(x => x.id === item.id ? { ...x, archived: !x.archived, name: x.name.trim() || 'Sem nome' } : x))}>{item.archived ? 'Reativar' : 'Arquivar'} {label}</button>
    </div>)}</div>
  </section>;
}
interface Props { definition: GameDefinition; busy: boolean; error: string; onDirty: (value: boolean) => void; onSave: (definition: GameDefinition) => Promise<boolean> }
export default function DefinitionEditor({ definition, busy, error, onDirty, onSave }: Props) {
  const [draft, setDraft] = useState(definition);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  useEffect(() => { if (!dirty) setDraft(definition); }, [definition, dirty]);
  const update = (patch: Partial<GameDefinition>) => { setDraft({ ...draft, ...patch }); setDirty(true); };
  return <form className="glass-panel games-definition" onSubmit={async event => {
    event.preventDefault();
    if (await onSave(draft)) setDirty(false);
  }}>
    <div className="games-toolbar"><div><span className="games-eyebrow">DEFINA ANTES DE MEDIR</span><h2>Como funciona este jogo?</h2></div><Settings2 size={28} /></div>
    <p className="games-muted">Dê seus próprios nomes às habilidades, ações e condições. Os modelos iniciais são sugestões que você pode editar e ampliar.</p>
    <fieldset disabled={busy}>
      <div className="games-fields">
        <label>Tipo de jogo (livre)<input required list="games-category-options" maxLength={100} value={draft.category} onChange={e => update({ category: e.target.value })} /></label>
        <datalist id="games-category-options">{gameTypes.map(type => <option key={type} value={type} />)}</datalist>
        <label>Nome da galeria<input required maxLength={80} value={draft.entityLabel} onChange={e => update({ entityLabel: e.target.value })} placeholder="Personagens, Cartas, Unidades…" /></label>
        <label className="games-check"><input type="checkbox" checked={draft.hasEntities} onChange={e => update({ hasEntities: e.target.checked })} />Usa personagens, cartas ou outras peças</label>
        <label className="games-check"><input type="checkbox" checked={draft.hasRanked} onChange={e => update({ hasRanked: e.target.checked })} />Possui ranking ou modo competitivo</label>
      </div>
      <div className="games-definition-explainer"><span><Brain size={18} />Habilidades: o que você desenvolve</span><span><Workflow size={18} />Ações: o que acontece no jogo</span><span><Target size={18} />Métricas: o resultado observado</span><span><Tags size={18} />Contexto: em quais condições</span></div>
      <CatalogEditor title="Habilidades do jogador" label="habilidade" hint="Macro, controle de mapa, leitura, consistência… Use o vocabulário que faz sentido para você." items={draft.skills} disabled={busy} onChange={skills => update({ skills })} />
      <CatalogEditor title="Ações e habilidades do jogo" label="ação" hint="Ataques, skills de personagem, trocas, compra de itens ou jogadas. Essas ações poderão compor a sequência de um registro." items={draft.actions} disabled={busy} onChange={actions => update({ actions })} />
      <section className="games-definition-section"><div className="games-toolbar"><h3>Métricas que você quer acompanhar</h3><button type="button" className="btn secondary" disabled={draft.metrics.length >= 100} onClick={() => update({ metrics: [...draft.metrics, metricDefinition()] })}><Plus size={14} />Definir métrica</button></div>
        <p className="games-muted">Escolha nome, unidade e como interpretar o número. Uma habilidade pode ter várias métricas; descrições ajudam a manter medições consistentes.</p>
        <div className="games-definition-grid">{draft.metrics.map((metric, i) => <div className={'games-definition-item ' + (metric.archived ? 'is-archived' : '')} key={metric.id}>
          <label>Nome da métrica {i + 1}<input required maxLength={80} value={metric.name} onChange={e => update({ metrics: draft.metrics.map(m => m.id === metric.id ? { ...m, name: e.target.value } : m) })} /></label>
          <label>Unidade da métrica {i + 1}<input maxLength={30} value={metric.unit} onChange={e => update({ metrics: draft.metrics.map(m => m.id === metric.id ? { ...m, unit: e.target.value } : m) })} placeholder="%, pp, pontos, dano, segundos…" /></label>
          <label>O que medir / critério {i + 1}<input maxLength={2000} value={metric.description} onChange={e => update({ metrics: draft.metrics.map(m => m.id === metric.id ? { ...m, description: e.target.value } : m) })} /></label>
          <label>Habilidade relacionada {i + 1}<select aria-label={'Habilidade relacionada ' + (i + 1)} value={metric.skillId} onChange={e => update({ metrics: draft.metrics.map(m => m.id === metric.id ? { ...m, skillId: e.target.value } : m) })}><option value="">Resultado geral</option>{draft.skills.map(s => <option key={s.id} value={s.id}>{s.name || 'Habilidade sem nome'}{s.archived ? ' (arquivada)' : ''}</option>)}</select></label>
          <label>Interpretação {i + 1}<select aria-label={'Interpretação ' + (i + 1)} value={metric.direction} onChange={e => update({ metrics: draft.metrics.map(m => m.id === metric.id ? { ...m, direction: e.target.value as typeof m.direction } : m) })}><option value="neutral">Depende do contexto</option><option value="higher">Maior é melhor</option><option value="lower">Menor é melhor</option></select></label>
          <button type="button" className="btn secondary" onClick={() => update({ metrics: draft.metrics.map(m => m.id === metric.id ? { ...m, archived: !m.archived, name: m.name.trim() || 'Sem nome' } : m) })}>{metric.archived ? 'Reativar' : 'Arquivar'} métrica</button>
        </div>)}</div>
      </section>
      <CatalogEditor title="Condições dos seus cenários" label="contexto" hint="Build, equipe, mapa, mods, adversário, tipo de carta… Cada campo poderá ser preenchido nos registros e usado para agrupar resultados." items={draft.contextFields} disabled={busy} onChange={contextFields => update({ contextFields })} />
      <p className="games-muted">Arquivar tira uma definição das novas medições e preserva o histórico. Mudanças de nomes e unidades não reescrevem os valores já registrados.</p>
      {error && <p role="alert" className="games-error">{error}</p>}
      <div className="games-toolbar"><span role="status">{dirty ? 'Definições não salvas' : 'Definições salvas'}</span><div className="games-board-tools">
        {dirty && <button type="button" className="btn secondary" onClick={() => { setDraft(definition); setDirty(false); }}>Descartar definições</button>}
        <button type="submit" className="btn primary" disabled={!dirty}>Salvar definições</button>
      </div></div>
    </fieldset>
  </form>;
}
