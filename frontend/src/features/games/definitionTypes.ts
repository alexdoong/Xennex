export interface NamedDefinition { id: string; name: string; description: string; archived: boolean }
export interface MetricDefinition extends NamedDefinition { unit: string; direction: 'neutral' | 'higher' | 'lower'; skillId: string }
export interface GameDefinition {
  category: string; hasEntities: boolean; entityLabel: string; hasRanked: boolean;
  skills: NamedDefinition[]; actions: NamedDefinition[]; contextFields: NamedDefinition[]; metrics: MetricDefinition[];
}
export interface SessionContext { definitionId: string; name: string; value: string }
export interface SessionEvent { actionId: string; actionName: string; actor: string; atSeconds: number; metricId: string; metricName: string; value: number | null; unit: string; notes: string }
export const namedDefinition = (name = ''): NamedDefinition => ({ id: crypto.randomUUID(), name, description: '', archived: false });
export const metricDefinition = (name = '', unit = ''): MetricDefinition => ({ ...namedDefinition(name), unit, direction: 'neutral', skillId: '' });
export const gameTypes = ['Personalizado', 'Ritmo e execução', 'Estratégia e personagens', 'Cartas'] as const;
export function definitionFor(category: string): GameDefinition {
  const rhythm = category === 'Ritmo e execução', cards = category === 'Cartas', strategy = category === 'Estratégia e personagens';
  return {
    category, hasEntities: !rhythm, entityLabel: cards ? 'Cartas' : 'Personagens', hasRanked: rhythm || strategy,
    skills: (rhythm ? ['Precisão', 'Consistência', 'Leitura'] : strategy ? ['Macro', 'Controle de mapa'] : cards ? ['Gestão de recursos', 'Leitura do oponente'] : []).map(namedDefinition),
    actions: (rhythm ? ['Trecho de treino'] : strategy ? ['Usar habilidade', 'Trocar personagem', 'Comprar item'] : cards ? ['Jogar carta', 'Defender'] : []).map(namedDefinition),
    contextFields: (rhythm ? ['Mapa', 'Modo', 'Mods'] : strategy ? ['Personagem', 'Build', 'Equipe', 'Adversário'] : cards ? ['Deck', 'Oponente', 'Tipo de carta'] : []).map(namedDefinition),
    metrics: (rhythm ? [metricDefinition('Precisão', '%'), metricDefinition('Performance', 'pp'), metricDefinition('Ranking', 'posição')] :
      strategy ? [metricDefinition('Dano', 'dano')] : cards ? [metricDefinition('Resultado', 'pontos')] : [])
  };
}
