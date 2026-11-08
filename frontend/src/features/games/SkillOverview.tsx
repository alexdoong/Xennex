import { Brain, Target, Trophy } from 'lucide-react';
import type { GameDefinition } from './definitionTypes';

export default function SkillOverview({ definition, disabled, onConfigure }: { definition: GameDefinition; disabled: boolean; onConfigure: () => void }) {
  const skills = definition.skills.filter(s => !s.archived);
  return <section className="games-roster"><div className="games-toolbar"><div><span className="games-eyebrow">SEU DESENVOLVIMENTO</span><h3>Habilidades e objetivos de análise</h3></div><button className="btn secondary" disabled={disabled} onClick={onConfigure}>Editar habilidades</button></div>
    <p className="games-muted">Escolha o que quer desenvolver e defina como observar. Os valores reais ficam nos registros do histórico.</p>
    <div className="games-skill-grid">{skills.map(skill => <details className="games-skill-card" key={skill.id}><summary><Brain size={28} /><strong>{skill.name}</strong><small>{definition.metrics.filter(m => !m.archived && m.skillId === skill.id).length} métricas relacionadas</small></summary>
      <p>{skill.description || 'Você pode explicar como avaliar esta habilidade em Definir jogo.'}</p>
      {definition.metrics.filter(m => !m.archived && m.skillId === skill.id).map(metric => <div className="games-skill-metric" key={metric.id}><Target size={14} /><span>{metric.name} · {metric.unit || 'valor'}</span></div>)}
    </details>)}</div>
    {!skills.length && <div className="games-visual-empty"><Brain size={36} /><h3>Suas habilidades, suas definições</h3><p>Adicione livremente o que quer acompanhar em “Definir jogo”.</p></div>}
    <div className="games-definition-explainer">{definition.hasRanked && <span><Trophy size={18} />Ranking / competição</span>}<span>{definition.metrics.filter(m => !m.archived).length} métricas definidas</span><span>{definition.contextFields.filter(c => !c.archived).length} condições de cenário</span></div>
  </section>;
}
