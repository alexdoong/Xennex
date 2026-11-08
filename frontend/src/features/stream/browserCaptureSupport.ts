export type ScreenCaptureAvailability = 'available' | 'insecure' | 'missing-api' | 'policy-blocked';

export interface BrowserCaptureStatus {
  screen: ScreenCaptureAvailability;
  secure: boolean | null;
  camera: boolean;
  watch: boolean;
  embedded: boolean | null;
  policy: boolean | null;
}

// Capability detection, not a mobile/user-agent blacklist. New mobile browsers
// exposing screen capture must be allowed to request the system picker.
export function browserCaptureStatus(): BrowserCaptureStatus {
  const secure = typeof isSecureContext === 'boolean' ? isSecureContext : null;
  const media = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices;
  let policy: boolean | null = null;
  let embedded: boolean | null = null;

  try {
    const documentPolicy = typeof document === 'undefined'
      ? undefined
      : (document as Document & {
          permissionsPolicy?: { allowsFeature(name: string): boolean };
          featurePolicy?: { allowsFeature(name: string): boolean };
        });
    const api = documentPolicy?.permissionsPolicy ?? documentPolicy?.featurePolicy;
    if (api) {
      policy = api.allowsFeature('display-capture');
    }
    if (typeof window !== 'undefined') {
      embedded = window.self !== window.top;
    }
  } catch {
    // Unknown policy/frame context is not proof of a block.
  }

  const screen = resolveScreenAvailability(secure, media, policy);
  return {
    screen,
    secure,
    policy,
    embedded,
    camera: typeof media?.getUserMedia === 'function',
    watch: typeof RTCPeerConnection === 'function',
  };
}

function resolveScreenAvailability(
  secure: boolean | null,
  media: MediaDevices | undefined,
  policy: boolean | null,
): ScreenCaptureAvailability {
  if (secure === false) {
    return 'insecure';
  }
  if (typeof media?.getDisplayMedia !== 'function') {
    return 'missing-api';
  }
  if (policy === false) {
    return 'policy-blocked';
  }
  return 'available';
}

export function screenCaptureExplanation(status = browserCaptureStatus()): string {
  switch (status.screen) {
    case 'insecure':
      return 'Abra o Xennex pelo endereço HTTPS. Esta página não está em um contexto seguro para capturar a tela.';
    case 'policy-blocked':
      return 'A página que abriu o Xennex bloqueou a captura de tela. Abra o link da sala diretamente no navegador.';
    case 'missing-api':
      return 'Este navegador não disponibiliza captura da tela. Instalar o site como atalho não habilita esse recurso. No Android, a prévia do capturador Xennex pode enviar a tela para esta sala; ela precisa estar instalada no aparelho. Você pode continuar assistindo pelo site.';
    default:
      return 'O navegador oferece a API de captura. O compartilhamento ainda depende da autorização e do seletor do sistema.';
  }
}

export function screenCaptureFailure(error: unknown): string | undefined {
  const name = error && typeof error === 'object' && 'name' in error ? error.name : undefined;
  switch (name) {
    case 'NotAllowedError':
      return 'O sistema ou navegador não autorizou o compartilhamento, ou a seleção foi cancelada. Confira a permissão e tente novamente. Esse erro sozinho não confirma a causa.';
    case 'InvalidStateError':
      return 'Abra o Xennex em primeiro plano e toque novamente em Compartilhar tela para abrir o seletor.';
    case 'NotSupportedError':
      return 'Este navegador expõe a captura, mas não conseguiu executar este tipo de compartilhamento. Confira o suporte da versão instalada.';
    case 'NotReadableError':
      return 'O sistema não conseguiu ler a tela selecionada. Encerre a outra captura, se houver, e tente novamente.';
    case 'NotFoundError':
      return 'O sistema não disponibilizou uma tela para compartilhar nesta tentativa.';
    default:
      return undefined;
  }
}

export function browserCaptureReport(status = browserCaptureStatus()): string {
  const formatFlag = (value: boolean | null) => (value === null ? 'desconhecido' : value ? 'sim' : 'não');
  return [
    'Captura do navegador · diagnóstico v1',
    `tela: ${status.screen}`,
    `HTTPS/contexto seguro: ${formatFlag(status.secure)}`,
    `política permite captura: ${formatFlag(status.policy)}`,
    `página incorporada: ${formatFlag(status.embedded)}`,
    `API de câmera: ${formatFlag(status.camera)}`,
    `WebRTC: ${formatFlag(status.watch)}`,
  ].join('\n');
}
