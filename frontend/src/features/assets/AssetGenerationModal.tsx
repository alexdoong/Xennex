import { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { layoutComfyGraph, parseComfyGraph } from './comfyGraph';
import { parseImageMetadata } from './comfyMetadata';

type Tab = 'nodes' | 'summary' | 'original';
type Props = { name: string; metadata: string; onClose: () => void };

export default function AssetGenerationModal({ name, metadata, onClose }: Props) {
  const parsed = useMemo(() => parseImageMetadata(metadata), [metadata]);
  const graph = useMemo(() => parseComfyGraph(parsed.fields), [parsed.fields]);
  const layout = useMemo(() => graph ? layoutComfyGraph(graph) : null, [graph]);
  const [tab, setTab] = useState<Tab>(graph ? 'nodes' : 'summary');
  const [activeNode, setActiveNode] = useState('');
  const closeButton = useRef<HTMLButtonElement>(null);
  const graphViewport = useRef<HTMLDivElement>(null);
  useEffect(() => { closeButton.current?.focus(); }, []);
  const jumpToNode = (id: string) => {
    setActiveNode(id);
    const target = [...(graphViewport.current?.querySelectorAll<HTMLElement>('[data-comfy-node]') || [])]
      .find(element => element.dataset.comfyNode === id);
    target?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
  };
  const connected = new Set(graph?.links.filter(link => link.from === activeNode || link.to === activeNode)
    .flatMap(link => [link.from, link.to]) || []);
  return <div className="assets-operation-overlay assets-generation-overlay" role="presentation"
    onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}
    onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); onClose(); } }}>
    <section className="assets-generation-modal" role="dialog" aria-modal="true" aria-label={`Dados de geração de ${name}`}>
      <header><div><small>METADADOS DA IMAGEM</small><h2 title={name}>{name}</h2></div>
        <button ref={closeButton} className="title-btn" onClick={onClose} aria-label="Fechar dados de geração"><X size={20}/></button></header>
      <nav role="tablist" aria-label="Dados de geração">
        <button role="tab" aria-selected={tab === 'nodes'} disabled={!graph} onClick={() => setTab('nodes')}>Nodes {graph ? `(${graph.nodes.length})` : ''}</button>
        <button role="tab" aria-selected={tab === 'summary'} onClick={() => setTab('summary')}>Parâmetros</button>
        <button role="tab" aria-selected={tab === 'original'} onClick={() => setTab('original')}>Texto original</button>
      </nav>
      {tab === 'nodes' && layout && <div className="assets-generation-graph-viewport" ref={graphViewport} role="tabpanel" aria-label="Mapa de nodes">
        <div className="assets-generation-graph" style={{ width: layout.width, height: layout.height }}>
          <svg className="assets-generation-links" width={layout.width} height={layout.height} aria-hidden="true">
            {layout.links.map((link, index) => {
              const from = layout.nodes.find(node => node.id === link.from);
              const to = layout.nodes.find(node => node.id === link.to);
              if (!from || !to) return null;
              const startX = from.x + 240, startY = from.y + 72, endX = to.x, endY = to.y + 72;
              const curve = Math.max(40, Math.abs(endX - startX) / 2);
              return <path key={`${link.from}-${link.to}-${link.input}-${index}`}
                className={activeNode && (link.from === activeNode || link.to === activeNode) ? 'highlight' : ''}
                d={`M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}`}/>;
            })}
          </svg>
          {layout.nodes.map(node => <article key={node.id} data-comfy-node={node.id}
            className={'assets-generation-node' + (activeNode === node.id ? ' active' : connected.has(node.id) ? ' connected' : '')}
            style={{ left: node.x, top: node.y }} onClick={() => setActiveNode(node.id)}>
            <div className="assets-generation-node-title"><small>#{node.id}</small><strong title={node.title || node.type}>{node.title || node.type}</strong></div>
            {node.title && node.title !== node.type && <small className="assets-generation-node-type">{node.type}</small>}
            <div className="assets-generation-inputs">{node.inputs.map((input, index) => <div key={`${input.name}-${index}`}>
              <span>{input.name}</span>{input.from ? <button onClick={event => { event.stopPropagation(); jumpToNode(input.from!); }}>{input.value}</button>
                : <output title={input.value}>{input.value || '—'}</output>}
            </div>)}</div>
          </article>)}
        </div>
      </div>}
      {tab === 'summary' && <div className="assets-generation-panel" role="tabpanel" aria-label="Parâmetros da geração">
        <p>Estes dados vêm do arquivo e podem ter sido modificados. Prompt positivo e negativo indicam entradas da geração, não sua avaliação da imagem.</p>
        {parsed.summary.length ? <dl className="assets-generation-summary">{parsed.summary.map(([key, value], index) => <div key={`${key}-${index}`}>
          <dt>{key}</dt><dd>{value}</dd></div>)}</dl> : <p>Nenhum parâmetro reconhecido automaticamente. Consulte o texto original.</p>}
      </div>}
      {tab === 'original' && <div className="assets-generation-panel" role="tabpanel" aria-label="Texto original dos metadados">
        {parsed.fields.map(([key, value], index) => <details key={`${key}-${index}`}><summary>{key}</summary><pre>{value}</pre></details>)}
      </div>}
      <footer>{graph ? `${graph.nodes.length} nodes · ${graph.links.length} conexões · fonte: ${graph.source}` : 'Este arquivo não contém um fluxo de nodes reconhecido.'}</footer>
    </section>
  </div>;
}
