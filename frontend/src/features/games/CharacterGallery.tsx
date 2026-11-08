import { useState } from 'react';
import { Plus, Users, ArrowUpRight } from 'lucide-react';
import type { GameCharacter } from './visualTypes';
import { colors } from './visualTypes';
import ImagePicker from './ImagePicker';

interface Props { label: string; characters: GameCharacter[]; busy: boolean; onChange: (characters: GameCharacter[]) => void; onPlan: (character: GameCharacter) => void; onEditing: (editing: boolean) => void }
export default function CharacterGallery({ label, characters, busy, onChange, onPlan, onEditing }: Props) {
  const noun = label === 'Personagens' ? 'personagem' : 'peça';
  const [imageLoading, setImageLoading] = useState(false);
  const [draft, setDraft] = useState<GameCharacter | null>(null);
  const edit = (character: GameCharacter | null) => { setDraft(character); onEditing(!!character); };
  return <section className="games-roster">
    <div className="games-toolbar"><div><span className="games-eyebrow">SEU ELENCO</span><h3>{label}</h3></div>
      <button className="btn secondary" disabled={busy || !!draft || characters.length >= 100} onClick={() => edit({ id: crypto.randomUUID(), name: '', role: '', notes: '', image: '', focus: 50, color: colors[0] })}><Plus size={16} />{label === 'Personagens' ? 'Novo personagem' : 'Nova peça'}</button></div>
    {draft && <form className="games-character-editor" onSubmit={event => {
      event.preventDefault();
      if (!draft.name.trim() || imageLoading) return;
      onChange([...characters.filter(c => c.id !== draft.id), { ...draft, name: draft.name.trim() }]); edit(null);
    }}><div className="games-portrait-preview" style={{ backgroundColor: draft.color + '25' }}>
      {draft.image ? <img src={draft.image} alt={draft.name || 'Prévia do personagem'} style={{ objectPosition: 'center ' + draft.focus + '%' }} /> : <Users size={56} />}
    </div><fieldset disabled={busy}>
      <h3>{(characters.some(c => c.id === draft.id) ? 'Editar ' : 'Criar ') + noun}</h3>
      <label>{label === 'Personagens' ? 'Nome do personagem' : 'Nome da peça'}<input required maxLength={100} autoFocus value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="Personagem, campeão ou carta" /></label>
      <label>Função / categoria<input maxLength={80} value={draft.role} onChange={e => setDraft({ ...draft, role: e.target.value })} placeholder="Dano, suporte, controle…" /></label>
      <label htmlFor="games-character-notes">{noun === 'personagem' ? 'Notas do personagem' : 'Notas da peça'}</label><textarea id="games-character-notes" maxLength={2000} rows={2} value={draft.notes} onChange={e => setDraft({ ...draft, notes: e.target.value })} />
      <ImagePicker label={noun === 'personagem' ? 'Escolher imagem do personagem' : 'Escolher imagem da peça'} value={draft.image} disabled={busy} onLoading={setImageLoading} onChange={image => setDraft(previous => previous ? { ...previous, image } : null)} />
      {draft.image && <label>Enquadramento vertical<input type="range" min="0" max="100" value={draft.focus} onChange={e => setDraft({ ...draft, focus: Number(e.target.value) })} /></label>}
      <div className="games-swatches" aria-label="Cor do personagem">{colors.map(color => <button type="button" className="games-swatch" key={color} aria-label={'Cor ' + color} aria-pressed={draft.color === color} style={{ backgroundColor: color }} onClick={() => setDraft({ ...draft, color })} />)}</div>
      <div className="games-toolbar"><button className="btn primary" type="submit" disabled={imageLoading}>{'Aplicar ' + noun}</button><button type="button" className="btn secondary" disabled={imageLoading} onClick={() => edit(null)}>{'Cancelar ' + noun}</button></div>
      {characters.some(c => c.id === draft.id) && <button type="button" className="btn secondary" disabled={imageLoading} onClick={() => { onChange(characters.filter(c => c.id !== draft.id)); edit(null); }}>{noun === 'personagem' ? 'Remover personagem do elenco' : 'Remover peça da galeria'}</button>}
    </fieldset></form>}
    {!characters.length && !draft && <div className="games-visual-empty"><Users size={36} /><h3>Dê um rosto às suas ideias</h3><p>Escolha suas próprias imagens e monte um elenco para criar equipes, rotações e estratégias.</p></div>}
    <div className="games-character-grid">{characters.map(character => <article className="games-character" key={character.id} style={{ borderColor: character.color + '70' }}>
      <button className="games-character-art" disabled={busy || !!draft} aria-label={'Editar ' + character.name} onClick={() => edit({ ...character })} style={{ backgroundColor: character.color + '25' }}>
        {character.image ? <img src={character.image} alt={character.name} style={{ objectPosition: 'center ' + character.focus + '%' }} /> : <span className="games-monogram">{character.name.slice(0, 2).toUpperCase()}</span>}
        <div className="games-character-caption"><small style={{ color: character.color }}>{character.role || 'Sem categoria'}</small><h3>{character.name}</h3></div>
      </button>
      {character.notes && <p className="games-character-note">{character.notes}</p>}
      <button type="button" className="btn secondary" disabled={busy || !!draft} onClick={() => onPlan(character)}>Usar no plano <ArrowUpRight size={14} /></button>
    </article>)}</div>
  </section>;
}
