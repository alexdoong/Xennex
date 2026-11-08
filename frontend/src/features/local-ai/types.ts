export interface AiSettings {
  provider: 'compatible' | 'ollama'; autoBudget: boolean; contextTokens: number; keepAliveSeconds: number;
  endpoint: string; model: string; memoryLimitPercent: number; additionalRamGb: number;
  additionalVramGb: number; useGpu: boolean; maxOutputTokens: number;
}
export interface AiMessage { id: string; authorId: string; authorName: string; authorRole: string; model: string; runId: string; purpose: string; context: AiContextReport | null; role: 'user' | 'assistant'; content: string; status: string; detail: string; createdAt: string }
export interface AiChat { project: AiProject | null; id: string; title: string; model: string; messages: AiMessage[]; updatedAt: string }
export interface ResourceDemand { ramGb: number; vramGb: number; source: string; detail: string; alreadyLoaded: boolean }
export interface OllamaModel { name: string; diskGb: number; loaded: boolean; loadedGb: number; loadedVramGb: number; loadedContext: number }
export interface OllamaServer { endpoint: string; models: OllamaModel[]; owned: boolean; capturedAt: string }
export interface AiRuntime { modelsDirectory?: string; installed: boolean; servers: OllamaServer[] }
export interface AiJob { messageId: string; runId: string; specialist: AiSpecialist | null; round: number; demand: ResourceDemand | null; id: string; chatId: string; status: string; detail: string; settings: AiSettings; createdAt: string }
export interface Resources { capturedAt: string; ramTotalGb: number | null; ramUsedGb: number | null; vramTotalGb: number | null; vramUsedGb: number | null; gpuName: string; warning: string }
export interface AiState { specialists: AiSpecialist[]; settings: AiSettings; chats: AiChat[]; jobs: AiJob[]; resources: Resources; paused: boolean; warning: string }
export const pending = (job: AiJob) => job.status === 'queued' || job.status === 'running';
export const statusName: Record<string, string> = { queued: 'Na fila', running: 'Respondendo', complete: 'Concluído', interrupted: 'Interrompido', cancelled: 'Cancelado', failed: 'Falhou' };
export interface AiSpecialist { id: string; revision: number; name: string; role: string; model: string; instructions: string }
export interface AiMember { specialistId: string; sharePlan: boolean; shareHistory: boolean; shareNotebook: boolean }
export interface AiPlanRevision { revision: number; content: string; createdAt: string }
export interface AiNote { id: string; specialistId: string; content: string; status: 'proposed' | 'hypothesis' | 'confirmed' | 'superseded'; origin: string; sourceMessageIds: string[]; createdAt: string; updatedAt: string }
export interface AiRun { id: string; question: string; purpose: string; planRevision: number; rounds: number; specialistIds: string[]; status: string; createdAt: string; finishedAt: string | null; generationSeconds: number; observedRamGb: number; observedVramGb: number; completedTurns: number; qualityScore: number | null; interventions: number; review: string }
export interface AiProject { revision: number; goal: string; members: AiMember[]; plans: AiPlanRevision[]; notes: AiNote[]; runs: AiRun[] }
export interface AiProjectEdit { revision: number; title: string; goal: string; plan: string; members: AiMember[] }
export interface AiContextReport { excerptMessageIds?: string[]; estimatedBytes: number; omittedMessages: number; sources: string[]; messageIds: string[] }
export interface AiRunRequest { requestId: string; question: string; purpose: 'discussion' | 'memory'; rounds: number; specialistIds: string[] }
