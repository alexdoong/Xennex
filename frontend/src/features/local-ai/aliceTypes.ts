export interface AliceSettings {
  python: string; checkpoint: string; endpoint: string; model: string; dialogueModel?: string;
  perceptionPython: string; perceptionModels: string; mirageModels?: string; seconds: number; ramFraction: number;
  attention: 'full' | 'learned' | 'quiet';
  memoryRecall?: 'preserve' | 'enabled' | 'disabled';
}
export type AliceModality = 'image' | 'audio' | 'text';
export interface AliceFrame { stream_id: string; sequence: number; label: string; modality: AliceModality | 'image_audio' }
export type AliceAction = 'name' | 'reply' | 'ask' | 'meaning' | 'relate' | 'correct' | 'recall' | 'feedback' | 'talk' | 'recall_feedback';
export interface AliceEvokedMemory {
  moment_ref: { acquired_at: number; known: boolean[]; source_context: { stream_id: string; source_sequence: number; captured_wall: number } | null };
}
export interface AliceAttentionAction { id: number; action: AliceModality | 'all' | 'quiet'; age_seconds: number; frame: Pick<AliceFrame, 'stream_id' | 'sequence'> | null }
export interface AliceVisualDetection { status: 'detected' | 'no_useful_box' | 'detector_error'; count: number }
export interface AlicePronunciation {
  status: 'learned' | 'heard' | 'ambiguous' | 'unmatched' | 'unusable_audio' | 'unattended' | 'duplicate' | 'conflicting_example';
  word: string | null;
  source_sequence: number;
}
export interface AliceRecord {
  request: { id: string; action: AliceAction; payload: { text?: string; word?: string; about?: string; relevance?: number; frame?: Pick<AliceFrame, 'stream_id' | 'sequence'> | null } };
  status: string; published?: number; revision?: number;
  result: { status: string; error?: string; question?: string; learning?: { learned?: boolean; kind?: string }; data?: { memory_text?: string; evidence?: { association?: { evocation?: { entries: AliceEvokedMemory[] } } }; proposal?: { text?: string; kind?: string } } } | null;
}
export interface AliceState {
  settings: AliceSettings; running: boolean; lastError: string; directory: string;
  scriptsAvailable: boolean; currentSnapshot: boolean; exitCode: number | null;
  snapshot: { phase: string; ticks: number; writer_commits: number; stopped?: string;
    interaction_state?: { records: AliceRecord[] };
    native_state?: { observations?: number; moments?: number; visual_region_moments?: number; last_visual_detection?: AliceVisualDetection | null; last_sound_association?: { name: string; count: number } | null; pronunciation_examples?: number; last_pronunciation?: AlicePronunciation | null; lifetime_moments?: number; forgotten_moments?: number; interpretation_versions?: number; attention_feedbacks?: number; attention_actions?: AliceAttentionAction[]; recall_feedback_actions?: { about: string; age_seconds: number }[] };
  } | null;
}
export const aliceStatus: Record<string, string> = {
  queued: 'Na fila', running: 'Processando', awaiting_reply: 'Precisa de uma palavra', completed: 'Concluído', failed: 'Não concluído',
};
