export type ComfyInput = { name: string; value: string; from: string | null };
export type ComfyNode = { id: string; type: string; title: string; inputs: ComfyInput[] };
export type ComfyLink = { from: string; to: string; input: string; output: number };
export type ComfyGraph = { nodes: ComfyNode[]; links: ComfyLink[]; source: 'prompt' | 'workflow' };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const text = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
const readJson = (value: string): unknown => { try { return JSON.parse(value) as unknown; } catch { return null; } };
const stringify = (value: unknown) => {
  if (typeof value === 'string') return value.slice(0, 400);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try { return JSON.stringify(value).slice(0, 400); } catch { return ''; }
};

function workflowTitles(value: unknown): Map<string, string> {
  const result = new Map<string, string>();
  if (!isRecord(value) || !Array.isArray(value.nodes)) return result;
  for (const node of value.nodes.slice(0, 200)) {
    if (!isRecord(node)) continue;
    const id = text(node.id), title = text(node.title);
    if (id && title) result.set(id, title.slice(0, 120));
  }
  return result;
}

function fromPrompt(value: unknown, titles: Map<string, string>): ComfyGraph | null {
  if (!isRecord(value)) return null;
  const entries = Object.entries(value).filter(([, node]) => isRecord(node) && typeof node.class_type === 'string' && isRecord(node.inputs));
  if (!entries.length) return null;
  const ids = new Set(entries.slice(0, 120).map(([id]) => id));
  const nodes: ComfyNode[] = [];
  const links: ComfyLink[] = [];
  for (const [id, raw] of entries.slice(0, 120)) {
    if (!isRecord(raw) || !isRecord(raw.inputs)) continue;
    const inputs = Object.entries(raw.inputs).slice(0, 50).map(([name, input]): ComfyInput => {
      const from = Array.isArray(input) && input.length === 2 && ids.has(text(input[0])) &&
        Number.isInteger(input[1]) && Number(input[1]) >= 0 ? text(input[0]) : null;
      const output = from && Array.isArray(input) ? Number(input[1]) : 0;
      if (from && links.length < 400) links.push({ from, to: id, input: name, output });
      return { name, value: from ? `#${from} · saída ${output}` : stringify(input), from };
    });
    nodes.push({ id, type: text(raw.class_type).slice(0, 120), title: titles.get(id) || text(raw._meta && isRecord(raw._meta) ? raw._meta.title : '').slice(0, 120), inputs });
  }
  return { nodes, links, source: 'prompt' };
}

function fromWorkflow(value: unknown): ComfyGraph | null {
  if (!isRecord(value) || !Array.isArray(value.nodes)) return null;
  const nodes: ComfyNode[] = [];
  for (const raw of value.nodes.slice(0, 120)) {
    if (!isRecord(raw)) continue;
    const id = text(raw.id), type = text(raw.type);
    if (!id || !type) continue;
    const inputs = Array.isArray(raw.inputs) ? raw.inputs.slice(0, 50).filter(isRecord).map((input): ComfyInput => ({
      name: text(input.name), value: input.link == null ? '' : `Link ${text(input.link)}`, from: null
    })) : [];
    nodes.push({ id, type: type.slice(0, 120), title: text(raw.title).slice(0, 120), inputs });
  }
  if (!nodes.length) return null;
  const ids = new Set(nodes.map(node => node.id));
  const links: ComfyLink[] = [];
  if (Array.isArray(value.links)) for (const link of value.links.slice(0, 400)) {
    if (!Array.isArray(link) || link.length < 5) continue;
    const from = text(link[1]), to = text(link[3]);
    if (ids.has(from) && ids.has(to)) links.push({ from, to, input: `entrada ${text(link[4])}`, output: Number(link[2]) || 0 });
  }
  return { nodes, links, source: 'workflow' };
}

export function parseComfyGraph(fields: [string, string][]): ComfyGraph | null {
  const prompt = fields.find(([name]) => name.toLowerCase() === 'prompt')?.[1];
  const workflow = fields.find(([name]) => name.toLowerCase() === 'workflow')?.[1];
  const workflowValue = workflow && workflow.length <= 2_000_000 ? readJson(workflow) : null;
  const promptValue = prompt && prompt.length <= 2_000_000 ? readJson(prompt) : null;
  return fromPrompt(promptValue, workflowTitles(workflowValue)) || fromWorkflow(workflowValue);
}

export type ComfyNodePosition = ComfyNode & { x: number; y: number };
export type ComfyLayout = { nodes: ComfyNodePosition[]; links: ComfyLink[]; width: number; height: number };

export function layoutComfyGraph(graph: ComfyGraph): ComfyLayout {
  const ids = new Set(graph.nodes.map(node => node.id));
  const links = graph.links.filter(link => ids.has(link.from) && ids.has(link.to));
  const indegree = new Map(graph.nodes.map(node => [node.id, 0]));
  const depth = new Map(graph.nodes.map(node => [node.id, 0]));
  for (const link of links) indegree.set(link.to, (indegree.get(link.to) || 0) + 1);
  const queue = graph.nodes.filter(node => !indegree.get(node.id)).map(node => node.id);
  for (let index = 0; index < queue.length; index++) {
    const id = queue[index];
    for (const link of links.filter(edge => edge.from === id)) {
      depth.set(link.to, Math.max(depth.get(link.to) || 0, (depth.get(id) || 0) + 1));
      indegree.set(link.to, (indegree.get(link.to) || 0) - 1);
      if (!indegree.get(link.to)) queue.push(link.to);
    }
  }
  const rows = new Map<number, number>();
  const nodes = graph.nodes.map(node => {
    const column = Math.min(depth.get(node.id) || 0, 40);
    const row = rows.get(column) || 0;
    rows.set(column, row + 1);
    return { ...node, x: 24 + column * 282, y: 24 + row * 192 };
  });
  return { nodes, links, width: Math.max(540, ...nodes.map(node => node.x + 250)),
    height: Math.max(300, ...nodes.map(node => node.y + 168)) };
}
