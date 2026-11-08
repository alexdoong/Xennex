import { PROTOCOL } from './protocol';

declare const __XENNEX_BUILD__: string;
export const STREAM_BUILD = typeof __XENNEX_BUILD__ === 'string' ? __XENNEX_BUILD__ : 'development';
export type EntryStage = 'signaling' | 'coordinator' | 'transport' | 'confirmation' | 'ready';
export type EntryFailure = 'signaling' | 'coordinator' | 'missing-room' | 'occupied-room' | 'transport' | 'confirmation' | 'closed' | 'rejected' | 'unknown';
export interface EntryObservation {
  ice?: string; connection?: string; gathering?: string;
  host?: number; public?: number; relay?: number; errorCode?: number; route?: 'direct' | 'relay';
}
export interface EntryDiagnostic {
  attempt: string; stage: EntryStage; result: 'pending' | 'connected' | 'failed';
  elapsedMs: number; negotiations: number; failure?: EntryFailure;
  ice: string; connection: string; gathering: string;
  candidates: { host: number; public: number; relay: number };
  errors: number[]; route?: 'direct' | 'relay'; timeline: { stage: EntryStage; elapsedMs: number }[];
}
const labels: Record<EntryStage, string> = {
  signaling: 'Serviço de sinalização', coordinator: 'Registro da sala', transport: 'Conexão direta / ICE',
  confirmation: 'Confirmação da sala', ready: 'Entrada confirmada',
};
const failures: Record<EntryFailure, string> = {
  signaling: 'O serviço de sinalização não respondeu. Confira conexão, bloqueios locais e disponibilidade do serviço.',
  coordinator: 'A sinalização do participante abriu, mas o registro da sala não terminou. Confira a disponibilidade do serviço de sinalização; isso ainda não é uma falha de mídia.',
  'missing-room': 'O identificador da sala não foi encontrado. Confira o código, a versão e se alguém criou a sala.',
  'occupied-room': 'O código já está registrado. Use Entrar na sala em vez de criar outra.',
  transport: 'A sinalização respondeu, mas o canal com a sala não abriu. Rede/ICE precisa de investigação; a causa ainda não foi confirmada.',
  confirmation: 'O canal abriu, mas a sala não confirmou a entrada. Confira a compatibilidade entre app e site.',
  closed: 'A sinalização foi encerrada. Tente entrar novamente.',
  rejected: 'A sala recusou a entrada. Confira a mensagem exibida e o limite de participantes.',
  unknown: 'A tentativa terminou sem causa confirmada. Compartilhe este diagnóstico para investigar.',
};
const count = (n: unknown) => typeof n === 'number' && Number.isFinite(n) ? Math.min(999, Math.max(0, Math.floor(n))) : 0;
const known = (value: unknown, allowed: string[], previous: string) => typeof value === 'string' && allowed.includes(value) ? value : previous;

/** Deliberately stores no room/peer IDs, names, URLs, SDP, credentials or arbitrary error messages. */
export class EntryDiagnostics {
  private started: number;
  private data: EntryDiagnostic;
  private now: () => number;
  constructor(now = Date.now) {
    this.now = now;
    this.started = now();
    this.data = { attempt: crypto.randomUUID().slice(0, 8), stage: 'signaling', result: 'pending', elapsedMs: 0,
      negotiations: 0, ice: 'unknown', connection: 'unknown', gathering: 'unknown', candidates: { host: 0, public: 0, relay: 0 },
      errors: [], timeline: [{ stage: 'signaling', elapsedMs: 0 }] };
  }
  private elapsed() { return Math.max(0, Math.min(86400000, this.now() - this.started)); }
  stage(stage: EntryStage) {
    if (this.data.result !== 'pending' || this.data.stage === stage) return;
    this.data.stage = stage;
    this.data.timeline = [...this.data.timeline.slice(-15), { stage, elapsedMs: this.elapsed() }];
  }
  negotiate() {
    if (this.data.result !== 'pending') return;
    this.stage('transport'); this.data.negotiations = Math.min(999, this.data.negotiations + 1);
    this.data.ice = 'unknown'; this.data.connection = 'unknown'; this.data.gathering = 'unknown';
    this.data.candidates = { host: 0, public: 0, relay: 0 }; this.data.route = undefined;
  }
  observe(value: EntryObservation) {
    this.data.ice = known(value.ice, ['new', 'checking', 'connected', 'completed', 'disconnected', 'failed', 'closed'], this.data.ice);
    this.data.connection = known(value.connection, ['new', 'connecting', 'connected', 'disconnected', 'failed', 'closed'], this.data.connection);
    this.data.gathering = known(value.gathering, ['new', 'gathering', 'complete'], this.data.gathering);
    for (const key of ['host', 'public', 'relay'] as const) if (value[key] !== undefined) this.data.candidates[key] = count(value[key]);
    if (Number.isInteger(value.errorCode) && value.errorCode! >= 0 && value.errorCode! <= 4096 && !this.data.errors.includes(value.errorCode!)) {
      this.data.errors = [...this.data.errors.slice(-7), value.errorCode!];
    }
    if (value.route === 'direct' || value.route === 'relay') this.data.route = value.route;
  }
  finish(failure?: EntryFailure) {
    if (this.data.result !== 'pending') return;
    if (!failure) this.stage('ready');
    this.data.failure = failure; this.data.result = failure ? 'failed' : 'connected'; this.data.elapsedMs = this.elapsed();
  }
  snapshot(): EntryDiagnostic { return structuredClone({ ...this.data, elapsedMs: this.data.result === 'pending' ? this.elapsed() : this.data.elapsedMs }); }
}

export function entryAdvice(entry: EntryDiagnostic): string {
  return entry.result === 'failed' ? failures[entry.failure || 'unknown'] : labels[entry.stage];
}
export function entryReport(entry: EntryDiagnostic, phase: string, alternative: boolean): string {
  const state = known(phase, ['idle', 'connecting', 'connected', 'reconnecting', 'error', 'closed'], 'unknown');
  return [
    `Xennex Live · ${PROTOCOL} · build ${STREAM_BUILD}`,
    `Tentativa: ${entry.attempt} · estado: ${state} · resultado: ${entry.result}`,
    `Etapa: ${labels[entry.stage]} · tempo: ${(entry.elapsedMs / 1000).toFixed(1)} s · negociações: ${entry.negotiations}`,
    `Configuração: ${alternative ? 'alternativa habilitada' : 'padrão P2P'} · rota observada: ${entry.route || 'desconhecida'}`,
    `ICE: ${entry.ice} · transporte: ${entry.connection} · coleta: ${entry.gathering}`,
    `Candidatos: locais ${entry.candidates.host} · públicos ${entry.candidates.public} · relay ${entry.candidates.relay}`,
    `Códigos STUN/TURN: ${entry.errors.join(', ') || 'nenhum observado'}`,
    `Etapas: ${entry.timeline.map(item => `${labels[item.stage]} @ ${(item.elapsedMs / 1000).toFixed(1)}s`).join(' → ')}`,
    entryAdvice(entry),
    'Candidatos e códigos isolados não comprovam a causa. Sem IPs, SDP, nomes, códigos de sala ou credenciais neste relatório.',
  ].join('\n');
}
