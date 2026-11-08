type Node = { class_type: string; inputs: Record<string, unknown> };
type ImageMetadata = { source: string; summary: [string, string][]; fields: [string, string][] };

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const label = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
const reference = (value: unknown) => Array.isArray(value) && typeof value[0] === 'string' ? value[0] : '';

function comfySummary(prompt: string): [string, string][] {
  let parsed: unknown;
  try { parsed = JSON.parse(prompt); } catch { return []; }
  if (!record(parsed)) return [];
  const nodes = new Map<string, Node>();
  for (const [id, value] of Object.entries(parsed)) {
    if (record(value) && typeof value.class_type === 'string' && record(value.inputs))
      nodes.set(id, { class_type: value.class_type, inputs: value.inputs });
  }
  const summary: [string, string][] = [];
  const add = (key: string, value: unknown) => { const text = label(value); if (text) summary.push([key, text]); };
  for (const [id, node] of nodes) {
    const { inputs } = node;
    if (node.class_type === 'CheckpointLoaderSimple') add(`Checkpoint · nó ${id}`, inputs.ckpt_name);
    if (node.class_type === 'LoraLoader') {
      const strength = [label(inputs.strength_model), label(inputs.strength_clip)].filter(Boolean).join(' / ');
      add(`LoRA · nó ${id}`, `${label(inputs.lora_name)}${strength ? ` (modelo / CLIP: ${strength})` : ''}`);
    }
    if (node.class_type === 'KSampler' || node.class_type === 'KSamplerAdvanced') {
      for (const [key, name] of [['positive', 'Prompt positivo'], ['negative', 'Prompt negativo']] as const) {
        const source = nodes.get(reference(inputs[key]));
        if (source?.class_type === 'CLIPTextEncode') add(`${name} · nó ${id}`, source.inputs.text);
      }
      for (const [key, name] of [['seed', 'Seed'], ['steps', 'Steps'], ['cfg', 'CFG'],
        ['sampler_name', 'Sampler'], ['scheduler', 'Scheduler'], ['denoise', 'Denoise']] as const)
        add(`${name} · nó ${id}`, inputs[key]);
      const latent = nodes.get(reference(inputs.latent_image));
      if (latent?.class_type === 'EmptyLatentImage') {
        const width = label(latent.inputs.width), height = label(latent.inputs.height);
        if (width && height) summary.push([`Dimensões · nó ${id}`, `${width} × ${height}`]);
      }
    }
  }
  return summary;
}

export function parseImageMetadata(raw: string): ImageMetadata {
  try {
    const value: unknown = JSON.parse(raw);
    if (!record(value) || !record(value.fields)) throw new Error('Invalid image metadata');
    const allFields: [string, string][] = Object.entries(value.fields)
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string');
    const summary = comfySummary(allFields.find(([key]) => key === 'prompt')?.[1] || '');
    const fields = allFields.slice(0, 40);
    return { source: typeof value.source === 'string' ? value.source : 'Imagem', summary, fields };
  } catch { return { source: 'Imagem', summary: [], fields: [['Texto', raw]] }; }
}
