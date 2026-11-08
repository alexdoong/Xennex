# Compatibilidade e escolha de codecs —02/11/2026

A experiência principal do grupo é o site no Cloudflare. O app Windows adiciona
captura/áudio nativos; sua GPU ou presença não é requisito para assistir/compartilhar
pelo navegador quando essas APIs estiverem disponíveis.

## Contrato desta etapa

- Política local de codec: Automático (padrão), Compatibilidade, preferir H.264,
  VP8, VP9 ou AV1. Preferência não remove os demais formatos negociáveis.
- Identificar encode/decode anunciados pelo navegador; consultar MediaCapabilities
  para resolução/FPS/bitrate escolhidos quando disponível. supported/smooth/
  powerEfficient são estimativas, não comprovação de aceleração ou benchmark.
- Automático preserva a ordem do navegador em ausência/empate de evidências;
  prioriza opções indicadas como eficientes/fluidas quando há diferença reportada.
  Sem inferir capacidade pela marca, idade, nome ou presença de GPU dedicada.
- Negociar por conexão: remetente usa capacidade de encode, receptor de decode.
  Não exigir AV1 de toda sala. Perfis H.264, RTX e FEC originais são preservados.
  A extensão usa metadata opcional e SDP do PeerJS já existente, mantendo v3.
- Com PeerJS, sua opção documentada sdpTransform reordena apenas payloads de
  seções de vídeo; não modifica codecs/perfis/ICE, áudio ou remove alternativas.
- Consulta local em cache limitado, até quatro perfis simultâneos e prazo800ms;
  API ausente, erro ou consulta lenta retorna desconhecido. Primeira resposta de
  vídeo pode esperar essa consulta limitada; entrada e vídeos ativos não esperam.
  Chamada encerrada/substituída não pode ser respondida após consulta tardia.
- Espectador possui sua própria preferência local em Qualidade → Compatibilidade
  deste dispositivo. Ela não é imposta pelo transmissor ou pela GPU dele; mudar
  reconecta somente os vídeos assistidos nessa ponta, sem reiniciar sala/envios.
- Separar recursos: assistir WebRTC, captura de tela e câmera. Ausência de
  getDisplayMedia desabilita só essa fonte; não impede assistir às transmissões.
- Não alterar monitor/janela, iniciar hook ou reduzir resolução/FPS manualmente
  escolhidos para trocar de codec. Controle de qualidade/limite de upload permanece.
- Nenhuma contratação, relay ou configuração TURN nova. Nenhum inventário de GPU
  ou relatório completo do dispositivo é transmitido na sala.

## Etapas posteriores

Encoders GPU nativos AMF/NVENC/Intel/Media Foundation serão opcionais e terão
detecção real por adaptador, driver e formato, teste sintético e fallback explícito.
Não expor opções como disponíveis antes de implementar. Integração nativa não deve
exigir instalação do app nos espectadores do Cloudflare. Escalar qualidade por
receptor requer medições sustentadas e regras próprias; não igualar estimativas
MediaCapabilities a “melhor configuração garantida”.

Validação: capacidades ausentes/negativas/estimadas, dispositivo com suporte
limitado, listas disjuntas e SDP com áudio/RTX/FEC; negociação WebRTC real entre
pares com ofertas limitadas, entrada de participante antigo, desktop/mobile UI e
integração de sala. Sem capturar câmera/tela pessoais.

Referências: [WebRTC](https://www.w3.org/TR/webrtc/),
[MediaCapabilities](https://w3c.github.io/media-capabilities/),
[PeerJS](https://peerjs.com/docs/).

## Estado implementado

streamCapabilities.ts consulta encode/decode por perfil, limita cache16/5min,
até4 perfis pendentes/800ms e retorna desconhecido ao falhar. Automático move
somente candidatos com diferença positiva reportada; preserva a ordem em empate.
Compatibilidade prefere H.264/VP8 quando presentes, mesmo sem APIs de consulta.
Formatos desconhecidos/perfis e alternativas permanecem no SDP.

StreamCompatibilityOptions é compartilhado pelo painel de transmissão e recepção.
Preferência de assistir é local/opcional no storage, independente da preferência
do transmissor; pode renegociar seus vídeos sem afetar os demais. Nenhum relatório
de hardware é enviado; somente perfil opcional de resolução/FPS/upload na metadata
da chamada. Clientes anteriores continuam no protocolo v3 e usam SDP normal.

Passaram testes unitários, PeerJS com múltiplos transmissores/migração, negociação
WebRTC local VP8/H.264/AV1 e UI móvel limitada a VP8 sem detecção/captura de tela.
AMF/NVENC/encoder nativo direto permanecem etapa posterior; o pipeline JPEG do
app não foi substituído nesta entrega.
