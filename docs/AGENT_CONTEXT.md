# Xennex — arquitetura e contexto

## Isolamento de áudio por janela/aba e canal dedicado na Web — 08/11/2026

Adicionados em `frontend/src/features/stream/capture.ts` e `StreamCapturePanel.tsx`
dois modos de áudio sem instalação para os participantes que transmitem pelo site no
Cloudflare Workers (`xennex-live.alexdoong11.workers.dev`):
- **Somente janela ou aba (`audio: 'window'`, padrão na Web)**: solicita
  `displaySurface: 'window'`, `windowAudio: 'window'`, `systemAudio: 'exclude'`,
  `selfBrowserSurface: 'exclude'` e `restrictOwnAudio: true` no `getDisplayMedia`,
  abrindo o seletor do Chromium (Chrome, Brave, Edge, Opera GX) direto na aba Janela
  e bloqueando o áudio do sistema inteiro para não vazar chamadas do Discord ou sons
  do PC.
- **Canal de áudio dedicado (`audio: 'device'`)**: captura a tela/janela sem áudio do
  navegador (`audio: false`) e anexa a faixa de um dispositivo `audioinput` escolhido
  (`echoCancellation: false`, `noiseSuppression: false`, `autoGainControl: false`),
  permitindo enviar canais virtuais de jogo (SteelSeries Sonar, Voicemeeter, VB-Cable).
- **Validação e Deploy Cloudflare**: `npm test`, `npm run lint`, `npm run build`,
  `npm run build:web`, `scripts/tests/test_ci.ps1` e `browser-capabilities-ui.mjs`
  aprovados com código 0; publicado em `https://xennex-live.alexdoong11.workers.dev`
  (Version ID `0b352946-cfd3-4188-ad68-f671adb8f2e7`).

## Streaming no Android e alinhamento aos padrões de código — 08/11/2026

Concluída e padronizada a prévia nativa de transmissão de tela no Android em
`src/Android` (`me.xennex.live`, API 26+, SDK 35) iniciada na sessão anterior,
com compilação e verificação isoladas em `scripts/build_android.ps1` e
documentação em [ANDROID_STREAMING.md](ANDROID_STREAMING.md).

- **Caminho de captura e protocolo v3**: `MainActivity` coleta código/link e nome
  (incluindo preenchimento seguro por `xennex-live://share?room=CODIGO`, inclusive
  em `onNewIntent`), solicita consentimento explícito do `MediaProjectionManager`
  e inicia `CaptureService` (`foregroundServiceType="mediaProjection"`,
  `START_NOT_STICKY`). `AndroidCapture` e `CaptureSize` mantêm textura GPU,
  dimensões pares até 1280px sem upscale e ajuste de rotação (`onCapturedContentResize`
  no Android 14+ e `DisplayListener` em versões anteriores). `AndroidRoomClient`,
  `RoomRoster`, `PeerSignaling` e `PeerLink` conectam-se a uma sala v3 existente
  sem assumir coordenação, validando presença antes de enviar vídeo para até 4
  espectadores (orçamento agregado de 8 Mbps dividido por receptor).
- **Integração Web e Diagnóstico**: `browserCaptureSupport.ts` verifica suporte a
  `getDisplayMedia` por capacidade real (sem bloqueio por User-Agent), gera
  diagnóstico copiável sem dados privados e expõe o atalho `Abrir capturador Android`
  no `StreamCapturePanel.tsx` quando a API de tela está ausente. Em
  `RoomToolsPanel.tsx`, os campos de conversa, nota compartilhada e tarefas
  receberam `aria-label` explícitos para preservar a acessibilidade determinística
  após edição de texto.
- **Padrões de Código e Higiene do Repositório**: todas as classes Java e testes
  em `src/Android` e `browserCaptureSupport.ts` foram refatorados para código
  plano com guard clauses, responsabilidade única e zero avisos de depreciação no
  `javac` (`WindowMetrics`, `WindowInsets.Type.systemBars()`, extração tipada de
  `Parcelable` e `Notification.Action.Builder` com `Icon`). `Xennex.csproj` exclui
  `src\Android\**`, `.gitignore` ignora artefatos/caches Gradle e APKs, e
  `AGENTS.md`, `STREAMING.md` e `TESTING.md` foram atualizados.
- **Validação e Entrega v0.2.4**: `scripts/build_android.ps1` (`assembleDebug`,
  `testDebugUnitTest`, `lintDebug`), `npm test`, `npm run lint`, `npm run build`,
  `npm run build:web`, `compact-ui.test.mjs`, `browser-capabilities-ui.mjs`,
  `dotnet build -c Release` e `scripts/tests/test_ci.ps1` aprovados com código 0.
  - **Pacote Windows (`v0.2.4`)**: `Backup/Xennex-v0.2.4-win64.zip` (328,6 MB,
    SHA-256 `56E485AC3E7A22346D837C24A0715B163EC9C5DD7A65D2CE99F3B2FF86A8A10E`),
    executáveis da raiz sincronizados e assinados com certificado `alexdoong`.
  - **Pacote Android (`v0.2.4`)**: `Backup/Xennex-Live-v0.2.4-android.apk`
    (49,8 MB, SHA-256 `D63243B722AAA069C297F9AAD940CDCCA06FEA1F785043DCED71B61C758B0255`).
  - **Cloudflare (`v0.2.4`)**: publicado em `https://xennex-live.alexdoong11.workers.dev`
    (Version ID `54910786-3bd9-4c9a-9d6a-ee3239750fff`, `/xennex-stream.json`
    reportando `protocol: xennex-room-v3` e `version: 0.2.4`). Ensaio em aparelho
    Android físico permanece pendente.

## Alice — prática acústica explícita de palavras — 08/11/2026

Painel e publicador local aceitam uma palavra escrita junto a um WAV isolado.
O worker extrai uma sequência acústica sem transcrição. O núcleo compara
ritmo/forma com até 32 exemplos anteriores, vincula a recuperação ao momento
ensinado e pode se abster. A origem é externa, a consulta não ensina, e os
formatos portátil 9 e paginado 10 preservam o vocabulário sem alterar os nomes
visuais. Teste de ponta a ponta com o encoder instalado aprendeu dois exemplos,
reconheceu uma variação reservada, recusou uma palavra parecida e reabriu o estado.
No lote sintético reservado, 16/16 variações com as duas vozes ensinadas e 14/14
controles fora do vocabulário recusados. Generalização para voz nova e busca
em frase continuam abertas. [Resultados](ALICE_EPISODIC_CONTEXT.md)

## Alice — som recupera o nome de uma imagem lembrada — 08/11/2026

O painel aceita PNG e WAV como um mesmo momento e permite ensinar um nome só
à modalidade escolhida. A evocação implícita de áudio pode ler a imagem de
momentos anteriores e consultar o nome visual já aprendido. O recibo distingue
essa hipótese de reconhecimento direto e rejeita fontes posteriores ao áudio.
Disputa entre nomes apoiados se abstém. A avaliação local com o encoder
instalado obteve 4/4 em variantes de tons e ruídos. Na voz sintética acertou
2/2 reapresentações exatas e se absteve em 4/4 variações. A restauração
preservou os nomes visuais e o banco direto de nomes do áudio ficou intacto.
[Contrato e limites](ALICE_EPISODIC_CONTEXT.md)

## Alice — influência do parser no que é aprendido — 08/11/2026

O ensaio pareado com Qwen3.5 0,8B mostrou que o seletor de palavras rejeitava
atribuições claras ao confundir o papel com a pessoa. O protocolo contextual
v2 oferece o valor literal depois do verbo ou abstenção e bloqueia marcadores
explícitos de dúvida. Novas escritas exigem v2, com leitura de planos e fontes
legados. Após a mudança, dois relatos e uma correção chegaram aos pesos e
foram recuperados depois de reabrir, enquanto cinco controles se abstiveram.
A expressão livre foi comparada com o mesmo estado nas duas rodadas e revelou
erros de formulação que não alteraram o banco. A margem de RAM disponível
adiou a tentativa com o 4B.
[Procedimento e resultados](ALICE_DIALOGUE_COMPARISON.md#efeito-na-aprendizagem-de-relatos--08112026)

## Alice — detalhes visuais ligados a momentos — 08/11/2026

O inbox local aceita caixas explícitas ou a geometria de objetos de um JSON Mirage
vinculado ao SHA-256 da imagem. O worker visual instalado codifica até quatro
recortes e preserva a cena inteira. A memória conserva os detalhes apenas quando
atende a imagem. A evocação implícita usa uma correspondência regional clara para
selecionar um momento anterior e ler seu conteúdo multimodal. O score regional é
heurístico e não cria fatos, nomes ou novas experiências.

O arquivo de momentos lê formatos antigos e persiste detalhes nos formatos 7
(portátil) e 8 (com páginas externas). Detalhes acompanham a retenção do momento.
A entrada do painel segue em cena inteira. Uso e limites em
[ALICE_EPISODIC_CONTEXT.md](ALICE_EPISODIC_CONTEXT.md) e
[LOCAL_AI.md](LOCAL_AI.md#recortes-visuais-na-alice).

No ensaio com o encoder instalado, a consulta estrita à cena inteira resolveu
0/4 objetos desenhados em fundos trocados. O recorte resolveu 2/4 e recuperou os
respectivos vetores de áudio sintéticos. Duas canecas semelhantes ficaram
ambíguas e o controle com recortes trocados provocou dois episódios incorretos.
O JSON de importação foi testado com fixture. O detector Mirage não foi executado.

Na continuação, o Mirage Cactus 4.0.0 Windows x64 foi executado localmente e passou
a ser um provedor opcional de caixas no worker da Alice. O painel configura a
pasta e informa resultado/retidos; a geometria explícita tem prioridade e a
aquisição da cena é preservada após falta de caixas úteis ou erro recuperável.
O comparativo com 16 imagens desenhadas ou compostas a partir de fotos COIL-100
mostrou 0/7 evocações corretas para Mirage e cena inteira, 4/7 com caixa manual
e um erro com caixa manual. A opção fica desativada por padrão.

## Construção do conjunto antes de otimização isolada — 04/11/2026

Diretriz explícita do usuário: objetivo integral de streaming permanece, mas a
execução deve construir a estrutura total e conectar versões básicas dos módulos
antes de insistir em testes de uso, FPS ou acabamento de uma peça. Um problema
local pode ser resolvido pelo restante da arquitetura. Registrar limitações e
seguir integrações independentes; bloquear por compilação/contrato quebrado,
segurança, perda de dados ou ciclo de vida inseguro. Não voltar ao ciclo de testar
JPEG em segundo plano repetidamente antes de conectar o conjunto.

STREAMING_ARCHITECTURE.md mapeia as 48 tarefas, fronteiras, dependências e donos
dos recursos. STREAMING_PLAN.md recebeu nova ordem e próxima rodada; critérios
de entrega e escopo foram preservados. Mapa completo não significa implementação
completa. Sessão/transporte/voz/operações compartilhadas e integração nativa
seguem como trabalho real, não marcado concluído.

Primeira consolidação: CaptureFramePipeline unifica consumidor JPEG, isolando
decoder/output/worker da coordenação em capture.ts. Instancia um backend por
captura, preserva trilha publicada durante fallback de decoder, fecha quadro
mesmo em cancelamento e não transforma falha do worker em simples cancelamento.
Canvas continua padrão; generator/worker continuam experimentais internos.
Não houve benchmark manual, captura de jogo, deploy ou novo pacote neste lote.

capture-pipeline.test.mjs entrou em npm test: ownership, decode tardio, fallback,
buffer transferido, backpressure e rejeição de métricas inválidas. npm test,
lint (sem erros, com avisos existentes), build app/web e test_ci.ps1 passaram.
CI precisou sair do sandbox após DirectoryNotFound no Temp virtualizado dos
SecurityTests; a execução normal passou. Logs em bin/streaming-structure-*.log.
Testes com doubles não comprovam a integração real de WritableStream/WebView2,
desempenho em segundo plano ou compatibilidade física. Esses pontos permanecem
pendentes na etapa apropriada; o objetivo completo segue ativo.

## WGC→NV12→H.264→RTC validado; controle de banda em comparação — 03/11/2026

WgcProbeSource captura somente executável/classe/PID/HWND da própria fixture.
OpenGlFixture.c ganhou --wgc-fixture explícito (janela1280×720/quadrantes, sem
hook); modo hidden antigo permanece default. build_native_webrtc.ps1 -BuildFixture
compila cópia isolada. Capture timestamps usam SystemRelativeTime; superfícies
WGC vão direto ao conversor GPU/poolNV12, sem JPEG ou staging de pixels. No modo
WGC não são alocadas as duas texturas BGRA sintéticas. Decoder independente e
vídeo recebido conferem cores. Fonte real1280×720/30 passou120/120; com navegador
realmente hidden também120 recebidos/decodificados e retomada17,9ms. Relatório
bin/streaming-qa/native-encoder-webrtc-1280-30-hidden-resume-wgc-fixture.json.

MFT com alvo6Mbps produziu≈24Mbps em1080p120; NAL filler era≈62% dos bytes numa
rodada. HardwareEncoderControl substituiu helper apenas de keyframe, usa tipos
ICodecAPI corretos, lê Mode/Mean e FrameRate dos tipos. Configurar controles antes
dos tipos reduziu saída para≈10,7Mbps, ainda acima do alvo. LowLatency(VT_BOOL)
e buffer187500bytes foram aceitos (HRESULT0), mas não corrigiram o desvio. Não
declarar bitrate cumprido por ler de volta6Mbps/120/1; só medição prova isso.

Iniciada comparação AMF direta opcional: SDK1.5.3, commit
57ee0cfb0e1a08d9041f77435653794c1b012be0, apenas headers/licença MIT sob bin/.
Adaptador C próprio Native/AmfEncoder.c e scripts/build_native_amf.ps1 compilam
sem warnings, ABI x64 estática. Runtime só LoadLibraryEx SYSTEM32/amfrt64.dll,
sem copiar/instalar driver; API mínima solicitada1.4.0. Ainda falta laço C# e
validação real desse backend; não é opção disponível no app nem suporte presumido
por marca. Media Foundation e caminho publicado permanecem. CI final pendente
desde as mudanças WGC/controle. Sem novo deploy/pacote neste lote.

## RTC nativo: TLS atualizado, nível negociado, PLI e hidden real — 03/11/2026

Objetivo completo segue ativo. Protótipo ainda isolado; nenhuma troca do Worker,
pacote oficial ou Cloudflare neste lote. MbedTLS3.6.7 LTS por commit fixado
068ff080b369adfac81509f9b57b2afabaf82dc5 substituiu3.6.5 e resolveu handshake
padrão local; scripts/build_native_webrtc.ps1 verifica pins/diff e grava manifesto
com SHA256 da DLL. libdatachannel0.24.6 preservado. Fingerprint adulterado falha
X509, peer failed e zero mídia. Teste negativo e baseline positiva passaram.

Consulta MediaCapabilities específica, limitada a1,5s, permitiu negociar
SPS424033/resposta42e033 e1080p120 no equipamento local (três flags true). Não
forçar nível maior se ausente/indisponível; stress acima do nível é modo distinto.
PLI→ICodecAPI(VT_UI4) no thread do encoder, coalescido/500ms, gerou novo IDR após
omitir inicial:1PLI/1force,2IDR,119 enviados/118 recebidos e decodificados.

Novo native-test-browser.mjs usa Edge com perfil próprio e connectOverCDP
noDefaults. Limites/resolução do caminho são validados e só o perfil temporário
sob bin/streaming-qa é removido. Navegação HTTP reativou visibilidade emulada;
HTML sintético no documento inicial permitiu hidden real, sem sobrescrever API.
720p30:54 recebidos/decodificados e0exibidos em hidden, retomada14,9ms.
1080p120:240 enviados/recebidos,224 decodificados; entrada120,01FPS, fase hidden
101 recebidos/99 decodificados/0exibidos, retomada18ms. Timeline confirma volta
visible; usuário pode tirar foco novamente, portanto não exigir visible final.
Relatórios e modos em NATIVE_ENCODER.md. Não declarar capturador JPEG atual
corrigido: falta integração real, áudio, carga/perdas, múltiplos pares e fallback.
CI anterior passou; repetir após streaming marker e alterações finais deste lote.

## Protótipo GPU por quadro e transporte nativo — 03/11/2026

Objetivo integral de streaming segue ativo. E01/E02 têm protótipo isolado em
scripts/tests/NativeEncoderTests, sem alterar Worker/app/pacote/site de produção.
MF/DXGI enumeram por adaptador; candidato0 ativou e não produziu saída, candidato1
funcionou na GPU local. Não assumir que inventário prova perfil/dispositivo.
BGRA→NV12 ocorre por quadro, pool4 liberado por timestamp; encoder H.264 hardware
e decoder Microsoft independente validaram todos os quadrantes/canais de cor.
1080p60/60quadros e1080p120/120quadros passaram; neste último entrada120,15FPS,
p95intervalo10,05ms, primeira saída13,44ms. Somente fonte sintética.

Preparado build portátil libdatachannel0.24.6/MbedTLS3.6.5 (commits fixados,
submódulos e ferramentas com hash), DTLS-SRTP consistente, sem serviço/TURN/custo.
Build passou; ensaio browser/SDP via pipe validou120 quadros720p30, entrada≈30,01FPS,
recebidos/decodificados120/120, cores RGB verificadas no Edge. Temporizador privado
de alta resolução evita jitter de Sleep(1), sem mudar resolução global do Windows.
Sem foco real (emulação desligada/janela minimizada), callbacks de exibição5;
visibilityState continuou visible.1080p120 recebeu/decodificou120/120, exibiu2,
mas ultrapassa nível3.1 anunciado e só é estresse opt-in, explicitamente marcado
no relatório. Não promover perfil acima do nível negociado ao produto.

MFT local precisou ConstrainedBaseline256; Baseline66 gerou42041f recusado.
DTLS padrão browser-active/native-passive falhou com feature indisponível;
resposta browser-passive passou sem desligar fingerprint/SRTP. Causa exata no
caminho inverso não confirmada. E03 continua parcial: papel padrão, capacidades/
nível, PLI, áudio sincronizado, pares/capturador real e distribuição pendentes.
CI anterior passou com exit0; gate final dos últimos contratos/temporizador em
bin/native-encoder-final-ci.log. Assinatura/pacote/site publicados anteriormente permanecem
os descritos abaixo. Foco/aba oculta continuam exigindo observação real, sem flags
que mascarem throttling. Nenhuma imagem pessoal capturada nesses ensaios.

## Início da execução integral do plano de streaming — 03/11/2026

Usuário ativou objetivo de implementar o plano agora que o grupo não está usando.
Objetivo permanece completo e ativo, sem declarar conclusão pelos primeiros itens.
Primeiro lote: R01/R02/R03 parciais, U01 implementado e D01 entregue. Plano
mantém tarefas externas e pesquisa explícitas; próximos módulos incluem chamada/
colaboração e protótipo de encoder GPU, preservando compatibilidade web/P2P.

Criados EntryDiagnostics/RoomEntryDiagnostic, stagePreferences e SessionBenchmark/
RoomBenchmark. Contratos e limites em STREAMING.md/TESTING.md. Entrada preserva
relatório após erro; não copia nomes, sala, peer IDs, IP/SDP, URLs ou segredos.
Tratadas exceções síncronas de criação/registro/canal, com retries limitados. Build
app/web tem marcador UTC. Layout salvo usa slots anônimos por ordem, com foco/
miniaturas e encaixe de2,5%; vídeo/áudio não são remontados na mudança de modo.

Integração Edge real anterior ao refinamento final: sala sintética,60s e dois
vídeos800×450/30, médias28,92/29,37FPS,30 amostras; arquivo agregado em
bin/streaming-qa/rtp-benchmark-60s.json. Registros brutos de tela não são salvos.
Não comprova baseline nativa completa ou causa da falha do amigo. TURN desligado.

Usuário lembrou lag ao ficar fora de foco. Acrescentados framesReceived/arrivalFps
separados de framesDecoded/fps, rótulos Recebendo/Decodificando/Exibindo e contagem
focused/unfocused/hidden/unknown no benchmark. Reset/gap longo mantém taxa desconhecida.
Playwright de integração não usa flags antithrottling. Testes reais atuais ainda
reportaram visible/focused; tentativa Edge minimizado também ficou visible. Não
apresentar isso como teste de aba oculta nem como correção de throttling.

Repetição nativa isolada sem build/benchmark concorrente:800×600, chegada28,1/
35,3/48,9FPS nos alvos30/60/120; processed≈30/41/54. Gate funcional passou, meta
alta não. Ensaio anterior concorrente chegou a5FPS; não atribuir causa só à rede.
Próximo lote deve medir/fixar ocultação real e avançar E01/E02 (encoder nativo),
sem esquecer módulos de chamada/colaboração e demais48 IDs do plano. CodecQuery
foi consultado: enumera codecs, mas não possui IsAccelerated; inventário WinRT não
prova encoder GPU/perfil. Não implementado nenhum encoder novo nesta rodada.

Passaram npm test, lint (somente12 avisos anteriores), builds app/web, integração
real Edge com minuto RTP/múltiplas fontes/áudio/migração/recarga/móvel, CI final e
smoke do pacote assinado em cópia isolada. Logs bin/stream-plan-*. Relatório novo
tem chegada/decode e contagem de foco; resultados reais sob bin/streaming-qa/.

Pacote oficial0.2.4 refeito por package_release.ps1,326,3MB; SHA256
8B42FB1EBC9B103EDD9E76C314451B4FC89B63671CD92FB0E0AC099649655EE9.
Raiz atualizada; instância principal encerrada conforme autorização anterior,
sem encerrar jogo. Backups before-streaming-plan-20261103-041437 e
before-focus-metrics-20261103-043355. Primeira tentativa de cópia encontrou lock
remanescente; inspeção confirmou término do processo e repetição copiou com hashes
iguais ao pacote. Dados/skins pessoais preservados; sem release/commit GitHub.

Cloudflare publicado19acaf94-1078-4aaa-bb7d-759b1e847e95, anterior/rollback imediato
e12e0ef9-509f-43d3-9b2f-09475c2876ea; antes do lotead351977-0b4d-4646-bfc2-cc3c1465e61d.
assets/index-laLhQhd1.js público igual por SHA256 ao dist; protocolo v3 e broker
503/turn_disabled conferidos. Nenhum novo serviço/secrets/billing ativado.

## Plano consolidado do streaming — 02/11/2026

Pedido do usuário: listar o que ainda falta implementar/melhorar e organizar um
plano completo. Criado docs/STREAMING_PLAN.md após conferir código, testes,
revisão histórica, contratos de codecs/TURN/hook e propostas fornecidas. Escopo
é streaming/chamada e funções das referências; demais módulos mantêm planos próprios.

Inventário separa pronto/experimental/pendente. IDs estáveis cobrem confiabilidade
R01–R06, nativo E01–E06, qualidade Q01–Q05, áudio A01–A04, UX U01–U04,
colaboração C01–C11, pesquisa X01–X07 e entrega D01–D05. Cada item tem prioridade,
dependência ou condição e critério de aceite. Incluídas matriz física/rede,
baseline sustentada, fallback e gate de entrega, sem promessa de FPS universais.

Próximo lote recomendado: R01–R04/D01 e protótipo isolado E01/E02. Falha do amigo
segue sem causa confirmada; aguardar evidência dessa ponta sem bloquear melhorias.
Prioridade web/Cloudflare, GPUs diversas, P2P, aviso silencioso e TURN desligado
preservados. Broker existente não significa relay ativo ou custo zero garantido.
ZIP Windows precisa incorporar codecs/aviso visual posteriores ao pacote do hook.

Esta entrega altera somente documentação; não ativa serviços, publica build,
troca protocolo nem implementa os itens do plano. Links adicionados em
STREAMING.md/STREAMING_REVIEW.md para evitar usar revisão antiga como backlog atual.

Validação: 48 IDs únicos e links locais conferidos, diff sem erro de whitespace.
CI geral terminou com código 0. Primeira execução falhou pelo diretório temporário
redirecionado do sandbox no SecurityTests; repetição fora do sandbox passou, sem
alterar testes ou expectativas. Não foram executadas novas capturas/hook/deploy.

## Aviso visual silencioso de compartilhamento —02/11/2026

Pedido do grupo: perceber quando alguém começa a compartilhar tela por brilho no
nome/degradê no Assistir; explicitamente sem som. Implementados nome iluminado,
botão com degradê/pulso2,4s×3 e selo Nova; contador no botão Pessoas e telas ajuda
quando painel está escondido/somente telas. Não abre painel, muda foco, assiste,
altera volume ou cria Audio/Notification automaticamente. Movimento reduzido
desativa animação, mantendo indicação estática. Selo limpa ao assistir/parar/sair.

StreamAnnouncements tem baseline da primeira presença, histórico por sessão
limitado2048 (sem perder IDs ativos), ignora câmera/telas próprias e evita repetir
por heartbeat, rename ou reaparecimento após migração. useStreamAnnouncements
fica no provider useRoom para manter estado entre compacto/janela completa;
durante reconnect conserva observação. Sem mudança de protocolo/rede/Worker.

Passaram unidade, npm test/lint (avisos antigos), builds app/web e CI geral.
UI real em sala/vídeos sintéticos: sem avalanche ao entrar, novo marcador com
painel escondido, sem autoplay, gradiente, nome, reduced-motion e reconhecimento
ao assistir; repetido no endereço público. Logs: bin/stream-announcements-*;
imagem QA em bin/capabilities-qa/new-screen-silent-highlight-mobile.png.

Cloudflare publicado ad351977-0b4d-4646-bfc2-cc3c1465e61d;
anterior/rollback40d1b997-7b58-475b-b3ca-5bc33ca4de72. TURN continua desligado,
sem serviço novo. Frontend local wwwroot gerado; executáveis/ZIP não foram
reempacotados nesta alteração de interface.

## Streaming web primeiro / grupo com dispositivos distintos —02/11/2026

Usuário esclareceu: amigos usam a ferramenta mais do que ele e normalmente pelo
Cloudflare. Priorizar site como experiência principal; app Windows é adicional.
Recursos avançados precisam ser opcionais, detectados por capacidade real/estimada
do ambiente e negociados por receptor. Não basear suporte em marca/idade de GPU,
nem exigir AMD/AV1/instalação do app para todos. Encoders AMF/NVENC nativos seguem
próxima etapa; não foram implementados/expostos como disponíveis nesta entrega.

Implementados streamCapabilities.ts e StreamCompatibilityOptions compartilhados:
auto/compatibilidade/preferir H.264,VP8,VP9,AV1; APIs WebRTC/MediaCapabilities de
encode/decode por perfil, estimativas rotuladas, erro/ausência/lentidão desconhecidos,
cache16/5min, no máximo4 perfis/800ms. Auto prioriza diferença positiva reportada;
empate/sem dados mantém browser. PeerJS sdpTransform reordena só payloads de vídeo,
mantendo formatos/perfis/RTX/FEC/áudio/ICE e fallback para espectador limitado.
Metadata opcional videoProfile; protocolo v3 preservado e sem inventário de GPU.

Quem assiste escolhe sua preferência em Qualidade → Compatibilidade deste
dispositivo, persistência local opcional. Reconecta só suas assinaturas; política
do transmissor não impõe AV1 ao receptor. Consulta fria antes de answer é limitada;
chamada encerrada/substituída não recebe resposta tardia. Sem getDisplayMedia,
desabilita apenas captura de tela; assistir WebRTC/câmera continuam por capacidade.
Frontend local gerado; ZIP da etapa anterior não foi reempacotado nesta entrega.

Validação: npm test (inclui APIs privadas/ausentes/lentas, SDP, posse de recepção,
cancelamento tardio), CI geral, builds app/web, lint (só avisos já existentes).
WebRTC real local: AV1 preferido→VP8-only e H264-only; H264 e AV1 modernos.
Integração PeerJS múltiplos transmissores/migração/eleição passou. UI390px simula
receptor VP8-only sem detecção nem captura; assistiu e mudou compatibilidade,
host mantido, sem overflow. Repetido no site público com sala/vídeo sintéticos.
Isso não valida placas físicas antigas/NVIDIA/Intel; necessário ensaio no grupo.

Cloudflare publicado:40d1b997-7b58-475b-b3ca-5bc33ca4de72;
rollback anterior8cab7830-3547-48fa-9ba9-6567ffea65eb.
HTML/JS referenciam assets/index-DBmJmN4r.js; protocolo xennex-room-v3 e broker
TURN503/turn_disabled verificados. Nenhum novo serviço, billing ou relay ativado.
Logs: bin/capabilities-*; contrato em docs/STREAMING_CAPABILITIES.md.

## Captura de jogo própria/OpenGL —02/11/2026

Usuário pediu capturar como OBS sem usar OBS. Implementados DLL/auxiliar próprios
x86/x64 com MinHook1.3.4 BSD2/HDE (fontes/licenças versionadas; nenhum código de
captura GPL/OBS), PBOs/fences, IPC anônimo limitado32MiB e processo/janela explícitos.
Módulo é desativado e fica residente até o jogo sair, evitando descarregar código
em retorno de outra thread. Reuso limpa buffers antigos; outra cópia/caminho é
recusada. Sem elevar privilégios, mudar jogo/anticheat/driver ou retry automático.

Probe autorizado carregou DLL própria assinada no osu!32 real em fullscreen
apresentado pelo usuário:30,0/60,0/119,7FPS brutos nos alvos30/60/120, conteúdo
mudando,0/0/1 skips, parada correta. Não salvou imagens ou encerrou o jogo. O jogo
precisa reiniciar antes de usar DLL do pacote em outro caminho. Resultado supera
DXGI1–2FPS desse caso; não generaliza a todos jogos/modos gráficos.

Backend game no CaptureWorker: assinaturas/publicador fixados, PID/HWND/início
validados, helper de arquitetura correspondente, cópia do último BGRA, JPEG com
orientação correta/limites/proporção, timer privado de1ms e timeout20s sem imagem.
BeginGameCapture passa pelo mesmo CaptureSessionService (posse/cancelamento/áudio)
e UI “Jogo OpenGL · experimental”; opt-in, sem trocar fonte/monitor sozinho.
Empacotador inclui quatro binários assinados+licença; fixture/compilador ficam fora.
Atualizador valida assinaturas do grupo quando presente; Worker repete antes de uso.

Testes próprios ocultos32/64: cores, estadoGL, resize,30/60/120 e três ciclos.
IPC/JPEG/socket autenticado com Workers terminados abruptamente:≈30/59/109–115FPS
nos alvos30/60/120. WebView2 isolada com fonte sintética e receptor WebRTC real:
≈29,9/57,4/83,1FPS,644×480 preservados. Não igualar FPS bruto a FPS no amigo;
decode/JPEG/canvas/encoder/rede ainda limitam. Ensaios não validam1080p120 ou rede
externa. CI, npm tests/build e teste de orientação/limites passaram nesta rodada;
pacote final assinado e validado. Revisão de contexto: intercepta wglDeleteContext,
invalida mesmo com reutilização do handle e recusa novo start até reiniciar jogo;
limpeza limitada por relógio real. Fixture confirmou jogo vivo após recriar GL e
recusa explícita, conflito de duas cópias e assinatura adulterada rejeitada.
Procedimentos/limites em docs/GAME_CAPTURE.md.

Entrega0.2.4: Backup/Xennex-v0.2.4-win64.zip,324,1MB,
SHA-256 F8A048FCEC711963E5607D20D87BFE1CE2C6C09D073B42D6A826A85716B8B4EA.
Raiz/Worker/quatro módulos iguais ao pacote; assinatura conferida pelo empacotador.
Self-contained final passou novamente no WebView2 isolado:≈28/52/101FPS recebidos
nos alvos30/60/120,644×480 preservados. Variação em relação ao primeiro ensaio não
representa regressão/ganho isolado; carga/temporização variam. CI final exit0;
npm test/build/build:web e lint exit0 (avisos já existentes). Backups anteriores:
Backup/before-game-hook-20261102-061825 e before-game-hook-context-20261102-063158.
App pessoal permaneceu fechado após teste; osu! real não foi encerrado pelo agente.

## Streaming — decode, fila recente e osu! real (01–02/11/2026)

Usuário pediu continuidade das propostas Gemini. Implementado CaptureFrameDecoder
com ImageDecoder/VideoFrame e fallback createImageBitmap (inclusive canvas que
recusa VideoFrame); codecs/quadros fechados e resultado tardio cancelado não
publicado. LatestCaptureFrame: um decode e um JPEG pendente substituível, limite
32MiB; sem backlog crescente, erro não prende a fila e socket fechado limpa
pendências. Mantém requestFrame por imagem, preserva áudio, dono e cancelamento.

CapturePipelineDiagnostics mostra caminho de decode, médias/p95, espera local,
idade desde evento do socket (não captura de origem) e quadros substituídos.
RTP acrescenta codec realmente negociado, médias encode/decode, jitter buffer,
perdas e diferenças NACK/PLI/drop/freeze. Dados ausentes/reset/intervalo antigo
ficam indisponíveis. Sem forçar codec ou inferir hardware de um nome de codec.

Benchmark WebView2 com JPEG85 sintético,26 amostras alternadas após6 de warmup:
720p bitmap2,43ms vsWebCodecs1,74;1080p4,07 vs3,17ms/p955,30 vs4,00.
Uma máquina/cena e submissão de desenho; não é garantia de FPS de rede. Preview
WGC confirmou caminho WebCodecs2,84ms médio/p956 e nenhuma substituição na janela
amostrada, sob carga distinta. Ensaio -DecoderBenchmark usa só pixels sintéticos.

Usuário autorizou testar osu! real, depois também janela/sem bordas; nenhum
quadro foi salvo e nenhum ajuste do jogo foi feito pelo agente. Windows build
26200: fullscreen do usuário causou DXGI ACCESS_LOST em loop, um quadro por
abertura: alvos30/60/120 deram1,43/1,46/1,35FPS locais e12/13/12 notificações.
WGC só da janela não produziu imagens suficientes (teste falhou explicitamente).
Não alegar que o teste sintético antigo resolveu fullscreen real. O probe antigo
encerrava com PASS ao obter poucos quadros; foi ajustado para falhar quando há
recriações repetidas, após registrar o resultado, sem reclassificar o ensaio antigo.

Ao usuário selecionar janela/sem bordas, probe DXGI novo mediu29,83/58,86/119,65FPS,
zero recuperações,251/499/1014JPEGs em≈9s/alvo. Até socket local; não no amigo.
Nenhuma janela pessoal foi capturada/salva fora do alvo do ensaio. Probe verifica
foco a cada25ms e encerra worker próprio ao sair do osu!/mudar monitor; só mantém
hashes e contadores. Não garante exclusão de todo quadro transitório entre troca
de foco e cancelamento; nenhum desses quadros é salvo ou enviado a participantes.
Relato primário comparável: github.com/obsproject/obs-studio/issues/14021. Evidência
compatível com limitação Windows/OpenGL, sem prova da causa interna nesta máquina.

CaptureRestartGuard corrige orçamento zerado por um único quadro:3 perdas próximas
sinalizam unstable;6 em10s encerram após um intervalo limitado de envio de aviso.
Fonte com imagem e2s estável limpa o histórico, inclusive cena parada. UI dá
orientação fixa/sanitizada sobre janela/sem bordas, não escolhe outra fonte nem
apaga falha independente de áudio. Testes simulam exatamente um quadro por
recriação, além de fallback, recursos, fila e RTP. Build/lint(12 avisos anteriores),
npm test e CI geral passaram; salas locais e publicadas testaram codec/decode,
áudio independente e migração com três publicadores sem exceções JS.

Pacote oficial assinado e executáveis raiz atualizados:
Backup/Xennex-v0.2.4-win64.zip,323MB,
FF5B316E121DE032DBEECB2722B0FE15B6CECB0897E07DA799EB9068F6654641.
Backup anterior Backup/before-decoder-pipeline-20261101-235811.
Cloudflare publicado com acesso já autorizado, nova versão
8cab7830-3547-48fa-9ba9-6567ffea65eb (anterior b7dad075-8858-4d5a-9b95-49eb00353e4a).
HTML confere com build e broker continua503/turn_disabled. Sem novos escopos,
secrets, relay real, alteração de cobrança, commit, reset ou mudanças em Data/skins.
Logs bin/decoder-*.log e bin/osu-real-*.log; especificações STREAMING.md/TESTING.md.
Encoder nativo, ROI/4:4:4, MoQ e FEC próprios continuam futuros e não foram
implementados por estas otimizações de decode/fila.


Validação final do pacote portátil passou WGC→GPU→WebCodecs, socket autenticado,
áudio nativo e recepção WebRTC nos alvos30/60/120. No ensaio sintético800×600,
recepção local mediu26,9/38,9/35FPS; híbrido720p/1080p24,8/20,2FPS, com a fonte
sintética também caindo para≈31FPS nos últimos casos. Não comparar diretamente
com o probe osu!120FPS, que mede só até o socket. Não declarar taxa fim a fim
atingida ou limitação removida porque qualityLimitationReason seja none. Esse
caminho de captura/canvas/encoder sob carga/visibilidade continua candidato a
investigação. Decode final WGC3,25ms/p957,5 e fila local0,23ms/sem substituições na
janela; houve variação grande no mapGPU sob carga. Funcionalidade passou; desempenho
não tem garantia. Integridade/preservação do pacote e assinaturas/cópias finais
conferidas; teste/servidor próprios encerrados e app raiz deixado fechado.

## Cloudflare — publicação do Xennex Live via Wrangler (01/11/2026)

Usuário autorizou conectar a conta e publicar após o uploader manual recusar a
pasta com wrangler.jsonc. Wrangler4.156.1 validou build/Worker em dry-run; login
por callback expirou e foi substituído pelo fluxo oficial de dispositivo. OAuth
inicial workers:write não dava acesso ao Worker. Revisão automática bloqueou
ampliação genérica; usuário aprovou explicitamente workers_scripts:write e
concluiu nova autorização. Escopos finais: account:read, user:read,
workers_scripts:write e offline_access; sem autorização de rotas. Não copiar
credenciais do armazenamento local para repo, frontend, docs ou chat.

Conta do Worker confirmada no painel e na API; account_id fixado em
cloudflare_pages/wrangler.jsonc para evitar destino errado. README corrigido:
Worker+Static Assets publica por Wrangler; uploader manual só serviria ao conteúdo
de dist num projeto exclusivamente estático. Não enviar pasta de fontes inteira.

Produção: https://xennex-live.alexdoong11.workers.dev
Versão anterior:4200db0c-350d-4282-85e3-57042cde8538.
Nova versão:b7dad075-8858-4d5a-9b95-49eb00353e4a, deployment
052bd2fa-d7a5-4f5a-b862-6bb17698c973,100% em2026-11-02T02:39:28Z
(01/11,23:39 em São Paulo). Histórico/metadados anteriores em
bin/cloudflare-deployments-before.json e bin/cloudflare-version-before.json,
não backup de credenciais ou cópia completa de código remoto. Preview URLs já
estavam habilitadas e permaneceram no padrão do Worker; não alteradas manualmente.

Publicados worker.mjs e assets compilados; TURN_ENABLED=false, ASSETS e binding
TURN_RATE_LIMITER. Observabilidade conforme configuração existente. Sem secrets
TURN, emissão de credenciais, serviço de relay real, alteração de cobrança ou
mudança de protocolo/P2P. Autorização de deploy não equivale a ativar TURN.

Verificações: HTML e hashes JS/CSS iguais ao build, manifesto xennex-room-v3 com
CORS público esperado, POST broker503/turn_disabled, origem não permitida403,
fontes worker.mjs/wrangler.jsonc/README404. HTTP Python sem navegador recebeu1010
na proteção Cloudflare; cliente padrão Windows e Edge funcionaram; nenhuma
proteção de segurança foi desativada. Relatório bin/cloudflare-deployment-verification.json.
Build web, CI geral e testes Edge no endereço REAL passaram: três publicadores,
áudio independente, layout, cancelamento, eleição/saída de coordenador e zero
exceções de navegador. Sala de teste separada; não tocar na sala ZEN dos amigos.
Log bin/cloudflare-browser-streaming.log. Nenhum commit, dados/skins preservados.


## Streaming — redução GPU antes do readback (01/11/2026)

Implementado primeiro incremento da análise das propostas externas: shader D3D11
reduz/rotaciona antes do map nos backends WGC e DXGI; GpuFrameEncoder unifica
JPEG/geometria/recursos reutilizáveis. Vortice.D3DCompiler3.8.3 (mesma licença MIT)
compila shader embutido. Sem transformações não usa shader; falta de suporte cai
para CPU nesta sessão; erros de dispositivo continuam na recuperação DXGI. JPEGs
independentes e fila de último quadro preservados. Sem mudança de rede/codec.

Telemetria limitada/versionada chega pelo socket autenticado e aparece no painel
Qualidade em componente separado, sem reiniciar histórico RTP. Distingue readback,
pré-JPEG, JPEG, média/p95 e decode/canvas. Parser rejeita campos inválidos; não
transmite dados da captura aos participantes da sala. Cena parada marca amostra
antiga em vez de inventar FPS. Map faz parte do pré-JPEG; não somar os dois.

Ensaio sintético GPU passou RGB, quatro rotações, odd/resize, no-upscale,
checkerboard/gradiente, JPEG imutável e fallback WARP10. Quadrantes4K→1080p/JPEG95,
24 amostras alternadas/aquecidas: CPU27,04ms/p9530,35; GPU4,16ms/p955,52.
Map33.177.600→8.294.400bytes/quadro; não benchmark PCIe/jogo/rede. WGC real próprio
800×600→640×480:29,49FPS/alvo30; pré-JPEG2,37/JPEG0,59ms, p954,04; decodeWebView≈19,85ms
é próximo candidato a investigação, sem presumir ganho. Fullscreen DXGI passou
47vermelhos/54azuis/3recuperações; não é teste direto do osu! do usuário.

CI geral, npm test/lint (12 avisos preexistentes), builds, ciclo nativo/auth/áudio,
GPU WGC através de socket/canvas e salas Edge com três publicadores passaram.
Sem deploy, ativação TURN, integração Cloudflare ou commit. Data/skins e trabalhos
Alice preservados. Detalhes e testes em STREAMING.md e TESTING.md.

Pacote oficial final assinado/validado; cópias da raiz conferem por SHA256.
ZIP `Backup/Xennex-v0.2.4-win64.zip` (322,1 MB):
`6B3421C44DC76D5B4BD1EF18D35EE4C9066B77E2E99CDA5EC8F25E714372DC42`.
Backup anterior: `Backup/before-gpu-readback-20261101-230454`.
Worker final single-file passou exclusivo/janela/exclusivo pelo socket autenticado
(37 vermelhos/55 azuis, duas notificações, sem imagens salvas). App portátil limpo
passou WGC GPU 800×600→640×480:30,58 quadros/s, pré-JPEG1,90/JPEG0,57ms,
p953,36ms e decode WebView15,37ms; três partidas295/296/298ms. Híbrido de navegador
Full HD53,7FPS/alvo60 nesta rodada (caminho distinto). Native/auth/áudio e teste de
integridade/preservação de dados no pacote passaram. Logs `bin/gpu-*.log`.
Processos de teste/servidor próprios encerrados; app principal deixado fechado.


## Streaming — fullscreen exclusivo e análise das propostas externas (01/11/2026)

Usuário relata osu! congelando último quadro ao entrar em fullscreen, inclusive
monitor. Preto pode ser carregamento real do mapa; não inferir falha pela cor.
Implementado backend de monitor DXGI opt-in no painel: Monitor / jogo fullscreen,
DXGI como seleção inicial dessa fonte e lista de monitores. WGC principal segue
manual; janela/browser nunca ampliam captura para um monitor silenciosamente.

GetCaptureMonitors/BeginDesktopCapture na ponte delegam à sessão com dono;
NativeCaptureService valida monitor disponível, argumentos e inicia worker local
autenticado com backend/display explícitos. Vortice.Direct3D11 3.8.3 no worker,
licenças MIT em assets/licenses/Streaming-DXGI.txt e saída licenses/ do pacote.
DesktopDuplicationCapture recria dispositivo/duplicação após perdas de modo,
confere GPU/LUID e identidade da interface do monitor após reabertura; tela trocada
falha fechada. Prazo 15 s para recuperar/obter quadro real; cena estática normal
não conta como perda. Still uses CPU/JPEG/canvas; não é zero-copy/hook de jogo.

CaptureSocketClient serializa status/JPEG com somente o último frame pendente,
para não perder a única imagem estática durante envio de status. Frontend mostra
recuperação fixa/sanitizada e preserva aviso de áudio. DXGI primeiro frame até20 s;
outros limites e propriedade mantidos. Cursor separado de hardware do Windows não
é composto neste backend; cursor do jogo pertence à imagem.

CaptureWorkerTests no CI simula perdas, orçamento, fonte reaberta sem imagem,
identidade alterada, recursos e concorrência. Teste fullscreen real foi autorizado
e passou em duas rodadas: exclusivo/janela/exclusivo, 49 vermelhos/55 azuis e
49/56 na revisão final, três eventos de recuperação, sem salvar quadros. Não foi
testado diretamente no osu! pessoal. UI monitor principal/secundário e mobile,
salas Edge com três publicadores e CI geral passaram. App principal encerrado
conforme autorização anterior de testes.

Pacote final oficial assinado/validado e executáveis da raiz conferem por SHA256.
Worker single-file testado por socket autenticado/porta efêmera durante a cena
fullscreen: 6 quadros vermelhos/55 azuis, duas notificações de recuperação,
exclusivo/janela/exclusivo sem salvar imagens. App portátil em cópia limpa passou
ponte de monitores (3), rejeição de ID inexistente, cena estática tardia, três
inicializações (290/307/295 ms), áudio e navegação bloqueada. Ensaio híbrido sintético
Full HD mediu53,7 FPS para alvo60 nesta rodada; não é garantia para jogos/redes.
CI final, npm test, lint (12 avisos anteriores/0 erros), builds e testes UI passaram.
Artefatos: bin/fullscreen-*20261101*.log, bin/streaming-*-20261101.log.
ZIP Backup/Xennex-v0.2.4-win64.zip:
99B38A3736E68DD05E82C457665D266F613BA09F8097A6B932CE74286E3265D3.
Backup anterior Backup/before-fullscreen-dxgi-20261101-224209. Data/skins e demais
trabalhos preservados; sem publicação, commit, integração Cloudflare ou TURN ativo.

Sugestões do Gemini tratadas como referência. Revisão detalhada com fontes em
STREAMING_REVIEW.md (seção01/11): GPU resident/encoder nativo é evolução possível;
não implementado. AMD lista RX906x/VCN5.0 em4:2:0, contrariando 4:4:4 universal;
DirectSR temporal exige dados ausentes da captura; QUIC/WebTransport/MoQ não são
substituição direta de P2P WebRTC. ROI, codec, FEC, sharpening e promessas numéricas
exigem capacidades e benchmarks. Não ativar serviços nem reescrever rede por esses
textos. Cloudflare/TURN continuam adiados/desligados; restante do trabalho preservado.

## Alice — evocação com percepções próximas, sem resetar o estado (01/11/2026)

Turno anterior foi progresso: seleção contextual persistida, controles e auditoria.
Próximo incremento testa fluxo real do observe, com vetores controlados e relógio
simulado0,2/0,1s. Pistas novas ficam na memória; evocar não fabrica áudio observado.
Piloto revelou saturação de16 créditos passivos antes do TTL. Agora substitui o
mais antigo, sem reutilizar IDs; retorno sobre crédito retirado é recusado.

Com crédito corrigido, sementes17/29/71 deram14/16,16/16 e13/16, falhando o critério.
Inspeção em17 encontrou penalidade contextual com pouco suporte superada por uma
candidata sem preferência. Hipótese registrada antes da revisão: atenuar bônus e
penalidade por1/(1+variância RLS), sem mudar características/alvo/cobertura25.
Regra fornecida, não probabilidade calibrada. Política2 versiona read_rule;
política1 restaura covered-linear-v1 e conserva a regra ao salvar. NativeGrounding10
e core57/58 inalterados. Não mudar silenciosamente políticas antigas.

Sementes reservadas41/53/89,96 feedbacks online cada:48/48 consultas;24/48 com
pesos zerados a partir dos mesmos estados. Todos os recortes conflito/reservado
passaram.196 impressões por estado treinado; avaliações acrescentam32. Fatores
originais inalterados e pistas novas somente visuais. Auditoria em processo novo
passou48/48 nos três native.pt sem feedback e conservou arquivos-fonte/pesos.
Auditoria de três arquivos da política1 passou outras48/48 consultas antigas.

8 contratos contextuais/7,672s,9 reativação/2,638s e11 runtime/26,104s passaram;
CI geral e build Release passaram. Falhas e sucessos em bin/AliceMemory/continuous-recall-*;
manifesto continuous-recall-manifest-20261101.json. Sem UI, LLM/encoder, sensores
pessoais, novo modelo, pacote ou Data. Ainda faltam fluxo ao vivo, foco semântico
real, feedback pela conversa e episódios abrangentes. Meta geral ativa.

## Alice — preferência contextual aprendida sem nomes (01/11/2026)

Usuário reafirmou experiência antes da nomeação: quente/hot podem nomear padrões
percebidos e lembrados; fala não define aprendizado. Critério comportamental
deve incluir reconhecimento, previsão e evocação não verbais, além da expressão.
Não transformar essa descrição filosófica em prova de sensação subjetiva ou
exigir experiência corporal para todo conceito/raciocínio.

RecallContexts guarda contexto anterior em pesos RLS ligados aos momentos;
RecallPreference aprende relevância por consequência externa de evocação real.
Crédito único,TTL60s, máximo16 pendentes,512 fontes e1M updates. Reranqueia antes
de até4 leituras/2 evocações; feedback não muda fatos nem contagem de experiências.
Características bilineares DCT16, prioridade/modalidades; nenhum rótulo de lugar/
assunto/ID-alvo. Contexto ausente não é preenchido retroativamente; aposentadoria
mantém identidades. NativeGrounding10 persiste contexto/política;1–9 legíveis,
core57/58 inalterado. Modo desligado conserva os pesos/registros já iniciados.

Critérios registrados antes do treino em ALICE_EPISODIC_CONTEXT.md. Seeds17/29/71,
96 feedbacks online cada:16/16 consultas por seed, inclusive combinação reservada
e conflito ambiente–assunto;8/16 ao zerar política ou contexto. Fatores apagados
eliminaram representações com rotas intactas. Auditoria em processo novo restaurou
os três snapshots com decoder atual e passou48/48 novas consultas sem feedback;
pesos da preferência e arquivos-fonte inalterados. Os relatórios originais tinham
checagem de ordem restaurada; o runner atual também consulta após restore.

6 contratos novos/2,272s,9 reativação/2,955s e11 runtime/27,189s passaram. CI geral
e build Release passaram. Artefatos contextual-recall-* em bin/AliceMemory;
manifesto contextual-recall-manifest-20261101.json registra fontes/provas.
Ensaio sintético128D,CPU1,sem encoder/LLM/nomes e com intervalos simulados120s.
Ganhos0,5 e0,25/projeção são fornecidos; faltam fluxo contínuo sobreposto, foco
semântico real, feedback pela conversa/painel e episódios abrangentes. Ambiguidade
factual204/215 permanece. Sem janela nativa, novos modelos, alteração do pacote ou
Data pessoal. Meta geral continua ativa.

## Alice — experiência não verbal, nomes posteriores e reativação implícita (01/11/2026)

Usuário reforçou que a gestão de memória pode ser implícita enquanto atenção/
reflexão estão em outra atividade. Memórias reativam representações da experiência,
como visão/som/sensação, não descrições textuais da cena. Capacidade de falar não
define aprendizado: experiência/associação pode anteceder o nome; quente/hot são
ligações convencionais com a experiência. Não reduzir todo conhecimento a contato
físico: raciocínio/estudo permanecem fontes previstas no plano. Não equiparar vetor
a sensação subjetiva nem afirmar que já existe um sentido térmico.

NativeMoments.related lê candidatas individualmente dos fatores, com limite2 e
até4 páginas; recall factual estrito mantém sua ambiguidade anterior. Reativação
opcional após percepção exclui o momento recém-adquirido e altera working e
dynamics.last.context para as próximas operações. Alvos observados e aprendizado
do estímulo atual ocorrem antes, sem vazamento de alvo. Atenção/links passam a
receber contexto influenciado por memória sem chamada de linguagem. Resposta
sintética/idle/quiet não fabrica percepção. Falha secundária de leitura é visível
e não desfaz aquisição válida. Saturação do contador1M preserva recência/checkpoint.

Modo --native-implicit-recall (negativo desliga, ausência preserva snapshot),
NativeGrounding9 ativo/1–8 legíveis sem ativação silenciosa; core57/58 preservado.
Ganho0,25 e prioridade são políticas fornecidas; contexto/relevância aprendidos,
acontecimentos abrangentes e integração geral com fala continuam pendentes.
O estado de trabalho/contexto são vetores persistentes, sem nova narrativa textual.

62 testes Python passaram:9 reativação/3,329s,15 momentos/14,677s,13 grounding/
16,509s,14 query/26,715s e11 runtime/28,766s. CI geral passou. Primeiras falhas eram
ordem esperada na fixture: importância/novidade fez a memória anterior superar a
mais recente; controles passaram a exigir preservação das duas, sem impor recência
como único critério. Estado/nomes permanecem critérios separados de correção da fala.
Associação imagem→som foi aprendida sem nomes, incluindo pista com pequena
perturbação não apresentada no treino; dois nomes inventados posteriores
evocaram o mesmo padrão. As entradas são vetores controlados, não treino do encoder.

nonverbal-reactivation-real-20261101-v2 passou na fonte real:204/215 recuperados
como duas representações visuais de mesmo conteúdo com referências distintas.
Pista veio do writer aprendido hami; sem encoder/LLM ou nova experiência. Fatores
apagados eliminaram conteúdo apesar de rotas intactas. Estado não verbal/contexto
mudaram, fontes aqueceram uma vez; nomes/fatos/contadores/origem conservados.
Restart preservou modo/estado e próximo tick não reaqueceu. A consulta factual
sobre dono continua ambígua no caminho antigo; não declarar episódio contextual
completo, aprendizagem geral ou companhia cotidiana alcançada. Sem janela nativa,
mudança de versão/pacote, novos modelos ou alterações em Data pessoal.

## Alice — retomada, evocação delimitada e revisão do conceito de episódio (01/11/2026)

Meta retomada pelo usuário. Sleep foi analisado como referência; usuário esclareceu
que aprendizagem, lembrança e comunicação/adaptação entre componentes devem ocorrer
durante a convivência, sem sono obrigatório. Bases pré-treinadas congeladas são
ponto inicial, não a definição final da mente. Reafirmou discutir hipóteses e
limitações de concepção em conjunto. À pergunta sobre evocação ambígua, explicou
relevância contextual dinâmica: restaurante/pedido versus restaurante/conversa
sobre compras. Também descreveu lembrança geral de um acontecimento, detalhes
ligados, motivos/estados e antes/depois (exemplo do banho). Contrato seguinte em
ALICE_EPISODIC_CONTEXT.md; preservar essa direção e não reduzir memória a fichas.

Fechado o incremento de validação que estava aberto desde13/10: diálogo v2 guarda
associação separada do about explícito, lê pesos sensoriais e de interpretação,
revalida sem aquecer a cada poll e conserva pending/registros retirados da fila.
Validação verifica nomes disponíveis no retrato e binding também após retirar job.
Backend falso de linguagem passou a ler a mesma associação. Ainda é evocação por
menção literal de um nome com episódio/relação únicos, não a arquitetura contextual
integrada acordada com o usuário. Não substituir o problema de múltiplas lembranças
por exigência permanente de escolher um relato manualmente.

25 testes de diálogo/94,186s +14 NativeStream/54,006s passaram. CI geral exit0 e
build .NET0. Falha inicial do controle de ambiguidade: nome de outro objeto não
havia sido aprendido; fixture corrigida e agora exige learned=true. Rodada seguinte
teve seis timeouts durante uso alto de RAM; testes de diálogo agora usam medição
de RAM determinística somente para o encoder falso, como NativeStream já fazia.
Admissão real não foi alterada; logs anteriores/falhas preservados.

Ensaio real dialogue-auto-real-20261101-v1 terminou inconclusivo:19 adiamentos por
resource_limit_crossed, nova entrada/intent salvas, sem nova aquisição. Fonte intacta
e processos encerrados. Diagnóstico independente dialogue-auto-lookup-20261101,
com gate de atenção explicitamente sintético e sem modelo/encoder, também não
atingiu o controle positivo: hami evoca204/215 e NativeMoments retorna ambiguidade.
Mesmo SHA de imagem, exposições distintas;204 sem relato,215 com autor/dono.
Não apagar204 ou filtrar pela resposta para fazer o teste passar. Precisamos evocar
candidatas separadas, considerar contexto e distinguir acesso geral/detalhes.
Fala4B+nova percepção não aprovada neste incremento; testes com fixtures não suprem
essa lacuna. Orçamento permanece75% padrão/90% apenas em ensaios finitos autorizados.

## Streaming — correções antes de conectar Cloudflare (31/10/2026)

Pedido atual: corrigir entrada na sala, carregamento/erro da captura nativa e FPS
antes de instalar/autenticar a integração Cloudflare ou ativar TURN. A leitura do
agent-setup foi somente análise; não houve instalação, autenticação ou deploy.

RoomCoordinator separa oferta/negociação (25 s) e join após open (10 s), corrigindo
timer que começava cedo demais; RoomClient alinha tentativa e limita entrada a
60 s, recua 2 s em perda explícita e limpa erro de sinalização na reconexão.
Sem logs da rede do amigo, não afirmar que a causa dele está confirmada/resolvida.

CaptureWorker guarda último JPEG para cliente tardio e usa CaptureFrameCadence
sem perda acumulada de fase. Canvas nativo solicita frame após decodificar e possui
fallback. Sessão consulta saúde do worker; sockets abortam tentativas com processo
encerrado. NativeCaptureService valida fonte e argumentos, retém worker até sua
saída e recusa janela inválida/minimizada. Aviso de ocupação agora fica visível.

Medição com captura da própria janela confirmou limites do pipeline WGC/JPEG/canvas:
não prometer 60/120 FPS só com teto maior. Alternativa implementada no app: vídeo
do navegador + áudio de processo. BeginBrowserCapture reserva sessão sem worker
de vídeo; usa áudio autenticado existente, não duplica áudio de sistema e preserva
vídeo em falha de som. Tela/janela/aba é escolha inicial; opções WGC permanecem.
Novos contratos/testes estão em STREAMING.md e TESTING.md.

Validação: CI completo, npm test, lint (sem erros; 12 avisos anteriores), builds
app/web/.NET/worker e Edge com três publicadores/migração passaram. Teste nativo
real em cópia limpa confirmou cena parada com cliente tardio, três inicializações,
token rejeitado, áudio por processo, navegação bloqueada e caminho híbrido sem
novo worker JPEG. Logs em bin/streaming-{unit,ci,browser,native}-20261031*.log.
O ensaio da própria janela teve fonte variável (último híbrido: fonte 16,3 FPS,
13,5 FPS decodificados em 1280×720/áudio ativo). É verificação funcional e medição,
não aprovação de 60/120 FPS sustentados nem comparação controlada de desempenho.
Primeiras inicializações WGC ficaram entre 265–395 ms nas rodadas locais.

Pacote oficial final gerado/assinado e testado em cópia limpa. Na rodada sem o
ensaio WGC animado anterior, caminho híbrido mediu 59,1 FPS recebidos em 1280×720;
ensaio separado Full HD mediu 1920×1080 e 54,7 FPS decodificados (alvo 60), ambos
com áudio nativo ativo e sem iniciar novo worker JPEG. Fonte é canvas sintético;
não demonstra desempenho sustentado de captura de jogos/120 FPS entre redes.
Raiz Xennex.exe e CaptureWorker conferem com Backup/Xennex-v0.2.4-win64.
ZIP: SHA256 E5A898CE95179E9B9286E39F0B8E16775EC2120B72CC824F4EEDF5D8C13C191B.
Backup anterior: Backup/before-streaming-fixes-20261031-223637. Data/skins pessoais
preservados; app foi encerrado com autorização para teste, sem reabertura automática.
Bundle cloudflare_pages/dist pronto, ainda sem publicação ou conexão da integração.

## Streaming — TURN opcional implementado, Cloudflare ainda desligado (31/10/2026)

Usuário autorizou implementar a alternativa, mantendo P2P como preferência e sem
consumo TURN no caminho normal. TurnFallbackPanel aparece após erro, abre acesso
explícito com código privado em memória e solicita lease do Worker somente ao
confirmar. RoomClient recebe lease isolado antes da entrada; bloqueia start com
alternativa durante sessão ativa, preserva outros peers e descarta credenciais no
retorno normal. Renovação é manual, sem recriar sala/vídeos. Diagnóstico registra
o caminho da entrada pelo par ICE escolhido, sem IP/SDP/credenciais.

Worker e wrangler.jsonc em cloudflare_pages: assets preservados, API separada,
TURN_ENABLED=false, secrets de API só no servidor, código de acesso, CORS explícito,
rate limit obrigatório, TTL servidor e erros sanitizados. Requisições desligadas/
inválidas não chamam a Cloudflare. Não houve deploy, criação de chave, relay real
ou ativação de cobrança. Controle de gastos continua pendente antes da ativação;
franquia/rate limit não garantem custo zero. Guia em STREAMING_TURN.md.

Mantido WebRTC: usuário esclareceu que quer capturar/excluir áudio de programas
Windows no browser. Esse limite é da captura/permissão; não resolvido por trocar
transporte. Captura nativa por processo permanece no app, sem abrir ponte para sites.

Passaram npm test (inclui Worker/leases e isolamento/renovação), lint sem erros
(12 avisos anteriores), CI completo e builds app/web. Edge com três publicadores
verificou ausência de consulta TURN no modo normal, broker desligado, opt-in,
renovação e preservação das outras mídias, volumes e migrações. Relay sintético
indisponível com P2P real não valida retransmissão Cloudflare; isso requer chave e
ensaio externo. Build isolado StreamingPreview atualizado. Ajustado teste de
migração para aguardar a mesma mídia assincronamente, sem relaxar expectativa.

## Streaming — preferência de TURN seletivo registrada (31/10/2026)

Usuário não quer alterar quem já conecta. Plano em STREAMING.md: TURN desligado
por padrão, sem consulta de credenciais; botão de tentativa alternativa após falha
de entrada, configuração isolada por participante e conexões saudáveis preservadas.
PeerJS atual configura ICE por instância, não por connect/call; recuperação de mídia
já ativa é escopo separado e não pode usar start/leave para reiniciar toda a pessoa.
Cloudflare TURN/Worker são candidatos, sem serviço ativado ou publicação; custo zero
continua requisito. Somente documentação nesta etapa, sem implementação de fallback.

## Streaming — investigar falha persistente de entrada (31/10/2026)

Amigo do usuário sempre teve timeout de entrada, com exemplo em 25/10. Logs
indisponíveis; causa ainda não confirmada. A mensagem corresponde à identidade
de sinalização obtida sem abertura do canal WebRTC da sala em 35 s. Padrão do
projeto sem TURN não atende todas as redes. Não instalar/configurar relay público
aleatório nem tratar a marca Brave como causa confirmada. Próximo teste útil é
mesmo PC/browser no hotspot, seguido do diagnóstico da tentativa quando disponível.

Acrescentado connectionDiagnostics para estados ICE/transporte/coleta, categorias
de candidatos e códigos STUN/TURN, sem IP/SDP/URLs/credenciais. Observadores ignoram
conexão antiga e são removidos no fechamento. Workspace oferece Copiar diagnóstico
após erro e explica que TURN pode ser necessário também para entrar. Testes unitários,
CI, lint e builds passaram; integração Edge verifica estados reais e cópia após
erro. Build StreamingPreview atualizado, bundle web gerado, sem deploy/commit.
Instrumentação não equivale a corrigir ou reproduzir a rede do amigo.

## Streaming — apresentação, palco e FPS recebidos (31/10/2026)

Usuário pediu interação familiar sem remover o estilo do Xennex. Compartilhamento
foi extraído para StreamCapturePanel: diálogo com fontes, resolução/FPS e ajustes
avançados. Barra superior mantém Transmitir, Pessoas e telas e Qualidade também
em Somente telas. A lista oferece Assistir/Parar. O palco ocupa a altura disponível,
com duplo clique para destaque e oito alças de borda/canto, preservando áudio e
volumes. streamStats distingue contadores RTP ausentes de zero e compartilha FPS
recebidos com tiles; exibição usa requestVideoFrameCallback como alternativa.
Diagnóstico expõe orçamento dividido entre cópias. Captura informa reduções de
formato identificáveis e automático não força 120 FPS nas constraints do browser.

Passaram npm test, lint sem erros (12 avisos anteriores), CI, builds app/web e
run_dev.ps1 -StreamingPreview -BuildOnly (.NET/worker sem avisos). Integração Edge
com três publicadores, navegação, oito alças/teclado, FPS recebidos, painel móvel,
áudio/volume e migração normal/abrupta passou. WebRTC local 1080p/60: recebido
1920 × 1080, amostra 57 FPS. Não garante desempenho entre PCs/redes diferentes.
Sem commit, pacote de release ou deploy público; teste em bin/StreamingPreview,
bundle web pronto em cloudflare_pages/dist. Detalhes e limites em STREAMING.md.

## Alice — pausa solicitada pelo usuário; evocação no diálogo em andamento (13/10/2026)

Usuário vai trabalhar/desligar o PC e pediu pausa. Preservar o incremento ainda
incompleto. dialogue_recall.py reconhece menções literais a nomes já aprendidos,
evoca representação pelos writers, consulta NativeMoments e vincula uma única
relação reportada ao episódio; ambiguidades/ausência de atenção ficam sem fato.
Não usa transcript como resposta nem compreende qualquer frase. DialogueLane
integra isso em dialogue_context_v2, preservando contexto antigo, seleção explícita
e modelo por trabalho. Contexto guarda associação separada; expressão e memory_text
usam o relato evocado. Revalidação consulta sem aquecer; montar contexto aquece
uma evocação sensorial suportada. Pesos factuais continuam lidos pelo proprietário.

Arquivos alterados neste incremento: scripts/alice_memory/dialogue_recall.py,
dialogue.py, dialogue_language.py e interaction_session.py. Regressão existente
test_alice_dialogue.py:18/91,052s passaram (dialogue-auto-recall-regression.log).
Esse teste ocorreu antes do ajuste final de reativação: NÃO considerar validada
a evocação automática. Faltam testes próprios de nome/episódio/pesos apagados,
ambiguidade, quiet, assinatura/revisão e restart, além de avaliação real com novo
texto/encoder e fala4B, CI final, documentação e manifest deste incremento.

Próxima ação: criar os testes de evocação e conferir suporte da fixture; depois
adaptar dialogue_probe.run para um ensaio com nome aprendido sem about escolhido,
preservando ensaio anterior e parser0,8. Pré-registrar critérios/orçamento antes
do teste real; não declarar sucesso se retornar ambiguidade ou copiar metadados.
Manter testes em segundo plano: usuário estava jogando e janela nativa interferiu.
Nenhuma nova execução de modelo foi iniciada neste incremento; último teste
observado é a regressão acima. Meta ampla pausada a pedido, não concluída.

## Alice — escolha separada do módulo de conversa (13/10/2026)

DialogueLane2 captura modelo por mensagem e guarda seleção opcional. Operation,
finish e restore validam o modelo do trabalho, mesmo depois de mudar a seleção.
Fila1 migra usando o parser original; Session6/core57/58 conservados. Runtime
--dialogue-model omitido preserva checkpoint, vazio usa parser; aceita também
LanguageCoordinator legado, adaptado antes da seleção. Painel/C# têm DialogueModel
opcional vazio compatível com settings antigos, validação e argumentos sem shell.
Mesma fila/slot, memória e relógio; parsers permanecem no modelo anterior. Não
alterou preferências pessoais nem adotou4B como padrão. Pré-treino ainda influencia
expressão; módulo separado não prova independência de personalidade.

40 testes Python:17 diálogo/94,299s +1 novo legado/8,529s +12 interação/27,931s
+10 runtime_store/18,510s. CI geral/116 IA local,frontend,UI headless e .NET passaram.
Falha inicial de Edge no sandbox preservada; headless com TEMP normal passou.
Sem janela nativa. dialogue-selection-real-v1 passou em runtime real:4B fala,
parser0,8;256 percepções/220 momentos intactos, pesos/nomes/origem conservados;
segundo processo voltou ao parser mantendo a resposta histórica identificada4B.
É replay de uma intenção sobre texto anteriormente adquirido, sem nova codificação
sensorial. Qualidade livre não aprovada; plano amplo continua ativo.
Auditoria em processo novo sem modelo confirmou384 bancos legados preservados,
pesos de interpretações/nomes e contadores intactos, histórico4B/parser0,8 e
próximo tick sem repetir aquisição. AST de223 arquivos Python válido; artefato
dialogue-model-selection-audit.json. Primeira tentativa do script de auditoria
falhou por import path; wrapperv2 acrescenta a raiz, sem mudar código da Alice.

## Alice — comparação controlada da expressão (13/10/2026)

dialogue_model_probe compara Qwen0,8B e4B já instaladas em oito casos previamente
registrados: atribuição atual/inicial, pesos apagados, fala gerada após apagamento,
troca de assunto, ausência de visão ao vivo, soma e informalidade. Contextos de
entrada sintéticos declarados; interpretações recuperadas dos pesos do estado
dialogue-real-v2/final.pt. Contextos de todos os casos e SHA da origem idênticos
entre modelos; ambos8/8 protocol_completed, quality_approved=false. Fonte intacta,
nenhuma nova percepção, download ou escrita autobiográfica. Controles apagam só
pesos residentes da interpretação e os restauram em finally, inclusive na falha.

Revisão manual:0,8 inventou mulher/vestido, alegou visão ao vivo e errou dois+dois;
4B corrigiu esses casos, mas disse “não tenho visão”/“só repito” e acrescentou
ressalvas desnecessárias. Recuperar pai/mãe e abster após apagar pesos não valida
texto livre ou aprendizagem por conversa. Nenhum modelo padrão/configuração foi
alterado. Próximo contrato registrado: escolha separada do módulo de expressão,
mesmo proprietário/slot, proveniência por trabalho e retomada compatível.

14 testes de diálogo/80,265s passaram, incluindo três novos controles de comparação
e falha do backend. CI geral exit0; sem testes de janela nativa após retomada do
usuário que estava jogando. Evidência/revisão em ALICE_DIALOGUE_COMPARISON.md e
bin/AliceMemory/dialogue-comparison-{08,4b}-v1/report.json; artefatos locais não
entram no Git. Meta ampla continua ativa, sem afirmar vida/mente completa.

## Alice — entrada sensorial de texto e diálogo experimental (13/10/2026)

PerceiveAliceText/gateway text publica UTF-8 exato (write_bytes evita LF→CRLF)
como frame real de origem person, sem seletor de arquivo. Talk{text,frame,about}
espera NativeStream/encoder, exige SHA/modalidade/origem corretos; quiet recebe
texto mas não inventa aquisição/episódio. DialogueLane integra InteractionSession6,
core57/58 preservado, slot único e relógio existente. Fila4,TTL300s/revisão3,
pending/checkpoint/restauração e reenvio sem segunda percepção. Contexto limitado
a estado operacional, duas falas geradas do mesmo assunto e relato escolhido lido
dos pesos. Assinatura invalida expressão se interpretação mudar antes da confirmação.
Gateway texto e envio são etapas distintas; UI conserva frame para retentar envio
da mesma mensagem após falha. Produção do texto pode preceder aceitação da intenção.

Expressão tem origem self, factual_text_verified=false/autobiographical_write=false;
não vira lição, feedback ou fato. Registro de fala própria não implica voz percebida.
Memória do assunto é texto separado, derivado do proprietário. UI aguarda published
antes de exibir propostas como entregues. Módulo recebe projeção verbal sem hashes,
IDs e provas completas; 2048 contexto/512 saída, demais parsers1024/256 inalterados.

11 casos novos/74,447s +65 regressão passaram (33/90,059 +32/54,738). UI headless,
frontend0, CI0 (111 IA local), .NET0 sem avisos. Primeiro backend de teste deixou
result.value vazio; corrigida publicação do fixture, falhas preservadas. Integração
real-v1 completou duas falas, falhou no limite de geração da terceira; contexto
extenso foi projetado e orçamento separado. dialogue-real-v2: encoder Gemma2 real,
Qwen0,8 instalada,3 textos/3 respostas;253→256 percepções/217→220 momentos,
nomes/interpretações conservados, origem intacta, retomada. Sem GUI/sensores novos.

Qualidade livre não aprovada: v1 inventou afirmações sobre formigas; v2 respondeu à
consulta de memória retomando formigas, embora texto do proprietário dissesse mãe.
Filtro de histórico por assunto + prioridade à pergunta atual: avaliação verbal
dialogue-topic-real-v1 mencionou mãe, mas com formulações imprecisas. Não alterar
critérios, apagar falhas ou vender isso como conversa cotidiana confiável. Ler
pesos corretamente e falar corretamente têm avaliações separadas. Aprender fatos
de conversas naturais e emissão/retorno de áudio continuam lacunas.
Auditoria em processo novo sem modelo:384 bancos antigos, pesos de interpretações
e nomes conservados;3 experiências textuais novas e próximo tick sem repetir
percepção. AST221 arquivos; dialogue-fresh-audit.json. Qualidade verbal ainda aberta.

## Alice — feedback externo ligado à atenção no canal vivo (13/10/2026)

Canal/sessão5 acrescentam feedback{text,action}. Proprietário encaminha à fila
NativeFeedbackLane existente; LLM interpreta só texto e não recebe referência,
histórico ou memória. Ação selecionada pelo usuário precisa estar pendente e válida
no momento da submissão (60s). Replay não escreve duas vezes; fila4 exerce
backpressure. Confirmação continua exigindo duas gerações. Após liberar job,
resta validação do resultado contra fonte aprendida, hash da mensagem, origem e
ação; fraude no request, downgrade e referência equivocada são recusados. Versões
anteriores1–4 migram; core57/58 mantido. validate_receipt compartilhado evita perder
proveniência ao retirar job cognitivo da fila.

Estado publica só escolhas elegíveis, com idade e frame quando há transporte.
Painel permite full/learned/quiet e seleção de escolha para avaliar, conservando
rascunho por contexto. Retorno pode ensinar valor de quiet sem episódio; avaliação
não é fato sobre o mundo ou sentimento próprio. Atenção tem ações/exploração
fornecidas; não é vontade geral nem percepção cotidiana validada.

8 novos/32,571s: positivo/negativo após mudança de situação, quiet sem episódio,
desconhecido/vencido/incerto, replay/durabilidade, retomada pending, fraude após
liberação, fila e história/ablação de valor.45 regressão/96,718s passaram. Primeira
tentativa excedeu contrato de tick60s no harness; corrigida em60+1, logs preservados.
feedback-channel-real-v1 com Qwen0,8 instalada e pista sensorial sintética: escolheu
quiet, feedback10→11/escritas2→3,253 percepções/217 momentos constantes, duplicação
recusada, origem intacta e restauração confirmada. UI headless passou; sem novo
teste de janela nativa durante jogo. Fontes e resultados em bin/AliceMemory/feedback-*.
CI0 (111 verificações IA local), build frontend0, .NET0 sem avisos/erros.
Auditoria em processo novo sem modelo conservou384 bancos antigos, pesos de
interpretações e nomes; confirmou uma atualização de feedback e próximo tick sem
nova escrita. AST216 arquivos Python; feedback-fresh-audit.json registra resultados.

## Alice — painel experimental e retomada pelo Xennex (13/10/2026)

AlicePanelService supervisiona uma sessão explícita separada do chat/Ollama.
Contratos tipados, COM declarativo e AlicePanel/useAlicePanel: iniciar, parar/salvar,
selecionar PNG/WAV/TXT, ensinar nome/relação, responder dúvida de nome, corrigir e
consultar por mensagem. Nenhum download, sensor ao vivo ou autostart. Configuração
75% padrão;90% exige duração finita até3600s. Fechar painel não encerra sessão;
encerrar aplicativo solicita salvamento e impede novo início. Processo observado
pelo handle próprio; relatório antigo não implica processo ativo. Logs limitados;
leitura de status permite substituição atômica. Stop cooperativo antes de kill da
árvore própria após20s. Gateway JSON não executa comandos de mensagens.

Primeira sessão copia estado compatível sob Data/ai/alice, conserva identidade e
contador de interação/transporte; estado original intacto. Recusa inboxes parciais,
preparação interrompida, lease alheio e fontes sensoriais pendentes não transportáveis.
Mensagens do gateway não importam Torch; preparar/perceber usa dependências existentes.
Rascunhos separados por operação e contexto; consultas/correções apontam mensagem
selecionada; ensinar nome/relação aponta frame selecionado. Não há diálogo livre.

Evidência:5 testes gateway/14,880s;8 consulta por referência/25,801s; navegador
headless passou fluxo e largura reduzida. Serviço real +Qwen0,8 recuperou mãe da
correção aprendida, sem nova percepção (253/217 constantes), parou/salvou/retomou,
hash de origem9750CC60A44E5B713096729ABA90449C8D2EE29B0455659FB92320C85510CD06 intacto.
WebView2/COM real passou write/read em bin/LocalAiNative-91281d61a7ef41ba894f9275e952dea3;
artefatos panel-native/{write,read}.json. CI final0 (111 verificações IA local),
frontend build0, .NET final0/sem avisos. Logs de tentativas anteriores preservados;
disputa de obj/ entre build/CI resolvida executando build sequencialmente.
Build de desenvolvimento; nenhuma publicação/instalação/version bump. M10 parcial:
orçamento compartilhado, percepção contínua e conversa natural ainda faltam.

Usuário pediu pausa porque a janela de teste interferia no jogo; retomada autorizada.
Não abrir outros ensaios nativos que disputem foco sem combinar; priorizar headless
e núcleo. O pedido sobre abelhas/formigas confirma memória imperfeita: familiaridade,
detalhes, importância e facilidade de reaprender são critérios distintos. Importância
não garante permanência, nem um erro de evocação prova apagamento dos pesos.

## Alice — consulta por mensagem e interpretação sem episódio sensorial (13/10/2026)

recall aponta UUID de relato aprendido; pergunta contém apenas Quem era antes,
E agora ou O que mudou. Proprietário captura versão de origem, referência imutável
do episódio e relação. Parser recebe só pergunta e seleciona perspectiva; não escolhe
referente nem recebe valor antigo/ID/memória. NativeMeaningQueryLane compartilha
worker/clock/fila4 entre consulta nominal antiga e consulta por mensagem. Resposta
lê pesos das interpretações, mantendo relato distinto de observação direta.

Mensagem substituída continua válida como referência do assunto: consulta atual
usa versões atuais, comparação conserva primeira/atual. Retirar episódio sensorial
não elimina necessariamente interpretação: consulta sem imagem/som se mantém e
informa ausência de retenção do episódio; não inventa percepção ou incrementa vida.
Peso de interpretação apagado retira sujeito da resposta, mesmo com texto/nomes
conservados. Mudança de conhecimento antes de entrega obriga recalcular. Poda
protege mensagem referenciada enquanto query está pendente. Envelope/sessão4 e
fila de meaning2 migram anteriores; externos57/58 mantidos. Mistura de consultas
nominais e referenciadas passa e formato antigo da fila migra sem replay.

reference-query-real-v1: Qwen0,8B, clientes separados em cópia da conversa perceptiva
real anterior, referenciando relato do dono já corrigido. Quem era antes → pai;
E agora → mãe; O que mudou → ambas. Sem nome/relação entre aspas nem janela no texto.
Seleção da mensagem é fornecida pelo cliente, não anáfora livre aprendida. Nenhum
encoder novo/sensor/ensino; observações253/episódios217/relatos6 constantes, fonte
intacta. Três retomadas portátil/atual/anterior sem modelo/reaprendizado preservam
pesos e384 bancos; controle apagado fica sem suporte.

Benchmark parcial12/14 accepted=false: Quem é recebeu perspectiva errada e Quem é
agora ficou incerto. Três perguntas fora da família/contraditórias usam restrições
fornecidas. A integração selecionada passou; não aprovar português geral por esse
resultado. Falha inicial nos testes veio de espaço ausente no regex de era/foi;
corrigida mantendo expectativas e log. Sem novo ciclo de prompts neste recorte.

199 nativos/424,114 s e98 coordenação/216,800 s passaram; novo teste de fila mista
adicionado depois e oito direcionados/28,525 s passaram (298 casos distintos).
CI0,214 Python AST/whitespace. Manifest reference-query-manifest.json preserva
fontes/artefatos/falha/retomadas. Meta ampla ativa: esclarecer recusas, intenção
aberta, pessoas, voz/GUI, confiança e desenvolvimento geral permanecem pendentes.

## Alice — relação e correção sem IDs no texto (13/10/2026)

relate liga uma frase sobre experiência selecionada à NativeStatementLane existente;
correct referencia o UUID da mensagem anterior. Papel literal é obtido por gramática
fornecida; LLM propõe apenas valor copiado da mensagem. Enum contém palavras dos dois
lados da cópula, sem fornecer a resposta correta. Proprietário valida palavra depois
da cópula, captura referência imutável e escolhe versão a corrigir. Modelos não recebem
IDs, memória ou valores antigos no parser. Nova cena não muda alvo; declaração de
imagem não pode apontar implicitamente um evento atendido somente por áudio.

Correção de relato sobre episódio sensorial já esquecido usa proveniência conservada,
sem recriar percepção. Referência substituída, papel diferente, sujeito inventado,
hipótese/negação/pergunta e alvo ausente são recusados. Pai permanece em initial;
mãe fica em current. Mensagem referenciada é protegida da poda enquanto correção
aguarda confirmação. Resultado confirmado, mesmo após job ser retirado, precisa
coincidir com fonte/versão/hash do relato. Envelope/sessão3, fila de relatos2 e
interpretações3 migram anteriores; externos57/58 continuam. Fontes contextuais
guardam hashes/modelo/prompt/plano, sem tabela de valores ou frase na interpretação.

context-report-real-v3: Qwen0,8B local, clientes separados durante execução e cópia
da memória perceptiva real anterior (hami/img215). Não carregou novos encoders nem
sensores. A informação dono era desconhecida; frase O dono dessa imagem é meu pai,
correção Na verdade, foi minha mãe e consulta comparativa por janela UTC aprendem
nos pesos e conservam ambas as versões. Texto não carrega episódio/versões; seleção
de experiência e referência da mensagem são fornecidas pelo cliente. Relatos4→6,
observações253/episódios217 constantes,42 commits e384 bancos antigos preservados.
Checkpoint fonte intacto. Três retomadas portátil/atual/anterior sem modelo/reensino,
nomes/relatos anteriores intactos; apagar só novos pesos retira o suporte das respostas.

Benchmark integral permanece accepted=false: variantes1/2/3:10/16,12/16,14/16.
Oito casos protegidos recebem restrições fornecidas. Variante3 ainda escolhe dono
em Porra, o dono disso é João e era em Corrigindo, era João; validação recusa,
sem aprender esses erros. Integração selecionada passou; português geral não está
aprovado. Tentativas/falhas/fontes antigas/raw proposals preservadas. Sem outro
ciclo de prompts após três variantes; esclarecimento por resposta humana e perguntas
por referência à conversa são próximos caminhos, além de intenção livre/voz/GUI.

Regressão também revelou resultado concluído após última captura periódica: uma
única captura final conservava aprendizado, mas não confirmava liberação da cópia.
Shutdown agora faz no máximo duas capturas finais quando falta confirmação, sem
avançar cognição/lançar worker. Teste força save_every3600 e exige duas gerações
antes de ack; passa. Teste inicial usou atributo inexistente para reduzir arquivo:
corrigido o fixture para NativeMoments(1,1) antes da primeira percepção; log mantido.

199 nativos/420,396 s +91 de coordenação/185,717 s =290 testes; dez contextuais
específicos/23,565 s, CI final0 e211 Python AST/whitespace. Manifest context-report-manifest.json
preserva artefatos/fontes/provas, incluindo falhas. Meta ampla segue ativa: formas
linguísticas abertas, identidades, confiança, consolidação, ações e convivência.

## Alice — relatos e correções por mensagens durante execução (13/10/2026)

O canal local agora encaminha report para NativeStatementLane e meaning para
NativeMeaningQueryLane, no mesmo proprietário/relógio/fila de inferência. Relato
atualiza pesos de interpretações versionadas; não vira percepção nem comprova
verdade. Consulta evoca nome sensorial aprendido e recupera a relação pelos pesos.
Correção conserva a atribuição inicial. Envelopes/sessão2 migram1; configuração e
recibos continuam1, snapshots externos57/58 preservados. Retomada valida vínculo
com a fila e igualdade do resultado cognitivo; cliente continua sem Torch.

Resposta calculada que espera confirmação em duas gerações é revalidada antes da
publicação. Correção, perda de suporte ou novo episódio que invalide a evidência
obriga recalcular/expressar; resposta já entregue conserva seu estatuto histórico.
Fila cheia aguarda, sem converter backpressure em erro terminal. Nenhum relato
recebido é usado para escolher sozinho entre episódios sensoriais ambíguos.

interaction-report-real-v3 passou com Qwen0,8B e encoder EmbeddingGemma2 instalados,
CPU, arquivos públicos bridge.png/speech.wav, fontes/manifestos verificados, teto
90% temporário. Imagem e áudio em dois processos/frames sucessivos. Antes do nome
hami a consulta se abstém; após ensino e relato ao pai, pista sem tempo encontra
três momentos semelhantes e pede quando aconteceu. Janela UTC externa seleciona
o frame: resposta inicial pai; correção explícita para mae; comparação conserva
pai/mae como relatos recebidos. Nome permanece ligado à imagem apesar do áudio
posterior.251→253 observações,215→217 episódios, nomes/fontes4→5, relatos2→4,
105 commits,384 bancos antigos e checkpoint fonte preservados. Não verifica
identidade humana do áudio nem interpretação aberta do conteúdo dos arquivos.

Três retomadas frescas do portátil/atual/anterior mantêm pesos, nomes anteriores,
versões e resultado sem modelo ou reensino. Apagar pesos das interpretações retira
os sujeitos da resposta; apagar pesos do episódio retira o suporte sensorial.
Tentativas preservadas: real-v1 sem reserva de RAM para quadro conjunto; real-v2
percebeu/ensinou, mas falhou no avaliador que assumia pista única. Não apresentar
esses ensaios como aprovados nem afirmar que resolveu captura simultânea contínua.

199 nativos/452,501 s +12 contratos do canal/66,898 s +43 conceituais/retenção/74,543 s
(254 testes), CI final0 e208 Python AST/whitespace. Artefatos/retomadas/fontes no
interaction-report-manifest.json. Português do report ainda literal, com momento,
aspas e versões; meaning aceita nome/relação/perspectiva/janela. Voz, GUI, diálogo
aberto, iniciativa aprendida, confiança e desenvolvimento geral seguem pendentes.
Meta ampla permanece ativa.

## Alice — interação local durante execução (13/10/2026)

InteractionInbox recebe name/reply/ask por arquivos atômicos e UUIDs; cliente CLI
não importa Torch. InteractionSession pertence ao mesmo ConceptualMind e usa suas
filas/relógio. Seleção pode esperar frame exato sem substituir por frame anterior;
resposta humana guarda vínculo original apesar de nova cena. Backpressure e estados
queued/running/awaiting_reply/completed/failed são limitados. Resultado só é publicado
após conteúdo/revisão iguais em duas gerações duráveis. Reenvio não repete ensino;
restauração rejeita vínculo/hash/forma inválidos. Recibos recentes512, pendentes
conservados; até32 registros na mente e128 arquivos examinados por leitura.
Snapshots57/58 acrescentam interactions, migração anterior inicia canal vazio.

Teste real interaction-runtime-real-v1: runtime finito, clientes independentes após
início, Qwen0,8B real, encoder visual fixture. Pergunta sobre Melo gerou esclarecimento
fornecido; nova imagem chegou; palavra de resposta ensinou frame0, não frame1.
251→253 observações,215→217 episódios, fontes4→5 e384 bancos antigos preservados;
14 commits, workers terminais e checkpoint fonte intacto. Duas retomadas frescas
sem modelo/repetição mantêm palavra e resultados. Metadados verificam vínculo de
frame, não reconhecimento visual entre as duas imagens. Sem sensores pessoais,
downloads, autostart ou alteração do modelo habitual. ask é consulta restrita,
não conversa aberta. GUI/voz, perguntas próprias e personalidade seguem pendentes.

213 regressões/442,003 s, sete contratos/22,176 s,36 conceituais/59,434 s e CI0;
207 arquivos Python com AST/whitespace verificados. Manifest interaction-manifest.json
registra fontes, checkpoints, páginas, testes e relatórios. Meta ampla segue ativa.

## Alice — resposta de esclarecimento ligada à experiência anterior (12/10/2026)

native_name_clarification oferece pergunta fornecida para job recusado/incerto.
reply_native_name aceita palavra/focus explícitos, ensina somente ref original e
registra horário real da resposta, com fonte external_word_reply e hashes. Não usa
LLM para resposta. Contexto esquecido/expirado, foco ausente e duplicação recusados.
Fila2 migra1; formatos55/56/native8 mantidos. Seleção explícita permite episódio
antigo retido; implícita segue30 s. Status/CLI expõem pergunta/resposta; UI/voz abertas
pendentes. Iniciativa fornecida, não curiosidade geral aprendida.

Ensaio reply-real-v1: Qwen0,8B recusou copula, pergunta fixou áudio; após31 s e novo
frame, Chuva aprendeu somente áudio antigo.251→255 observações,215→217 episódios,
quatro provas,384 bancos/colunas antigas preservados. Três retomadas frescas sem
modelo/duplicação. Pistas/resposta simuladas, sem captura pessoal. Benchmark completo
da linguagem continua falso; meta ampla ativa.
206 regressões/318,988 s,14 contratos/18,156 s, CI0 e três retomadas frescas.

## Alice — ensinamento de nome ligado ao episódio percebido (12/10/2026)

NativeNameLane compartilha worker; LLM extrai palavra, regras resolvem canal explícito
e algumas abstenções. Proprietário prende referência imutável/recebimento do episódio
recente; recuperação pelos pesos ensina somente modalidade atendida. Resposta
atrasada não ensina no frame novo; esquecimento/quiet/ambiguidade não fabrica alvo.
Provas native8: source_index/ref/issued/received_at/language hashes. Externos55/56
guardam fila. Migração sem inventar provas; restart sem repetir escrita. CLI expõe
arquivo/focus/moment e status native_name_jobs. Namespace32/fontes512 ainda limita
laboratório; crescimento e conversa/voz aberta permanecem na meta.

Qwen0,8B13/15, Qwen4B14/15, Gemma4B14/15, benchmark integral accepted=false.
Três associações reais de execução em pistas sintéticas e perturbações reservadas;
384 bancos/colunas antigas/nomes/relatos preservados,242→251 percepções e210→215
episódios. Ambiguidade/pergunta sem ensino. Três retomadas em processo novo mantêm
palavras/provas sem modelo ou repetição. Copulas ainda recusadas; não expor como
parser de conversa geral. Contrato label_fragment piorou e foi revertido; tentativas
e raw proposals do v6 preservados. Nenhum download/captura/configuração habitual
alterada. Meta ampla ativa, avaliação de personalidade/influência na fala pendente.
202 regressões/286,062 s, dez contratos de nome/12,178 s,36 conceituais/57,887 s,
CI final0,199 Python AST/whitespace. Integração verificada, linguagem geral pendente.

## Alice — retenção temporal de correspondências e reaquisição (12/10/2026)

NativeLinks3 aplica information-relaxation-v1 às direções RLS: ds/dt=-s/(tau*(1+s)),
tau86400 s fornecido. Vista envelhecida de pesos/covariância na previsão/antes do
update; somente coocorrência externa treina. Âncoras general/contextual por par;
tempo/consulta não reaquece nem escreve. Migração1/2 preserva pesos e inicia idade
no checkpoint. Familiaridade é suporte heurístico, não compreensão ou sentimento.
Cache espectral efêmero máximo8.358.048 B, sem novo tensor persistente. Nomes e
relatos factuais não usam ainda essa política; esquecimento conceitual segue pendente.

Sete testes novos; três bases rotacionadas no probe: detalhe reservado0,0994→~0,
componente frequente~1; pista detalhada se abstém com familiaridade0,9583. Reexposição
permite transferência à combinação-0,2 nunca ensinada (0,99997); controle frio sem suporte. Controle tau1e12
conserva detalhe. Tempo virtual300 s/tau10 s, currículo fornecido, sem modelo novo.
semantic-retention-v3 migra cópia de feedback-v8,384 bancos/242 observações/nomes e
relatos preservados; portátil/atual/anterior conservam pesos/âncoras. Primeira tentativa
de probe falhou por uso incorreto de RuntimeStore.submit; corrigida sem apagar logs.
Regressão conjunta192 testes/278,135 s e CI0; meta ampla continua ativa.

## Alice — feedback social direto em português (12/10/2026)

FeedbackLanguage propõe encouraging/discouraging/uncertain a partir de mensagem
externa; FeedbackLane vincula ação pendente do proprietário e compartilha o worker.
Somente social±1, benefício/esforço0. Validação conserva proveniência por hashes,
recusa vínculo inválido/duplicado e não permite auto-relato ensinar recompensa.
Pergunta/citação/hipótese se abstém; palavrão não implica reprovação. Glossário e
guardas lexicais fornecidos fazem parte do contrato, não aprendizado espontâneo.
Snapshots53/54 e atenção3, migração legacy sem inventar feedback histórico.
Runtime expõe flags de arquivo/ação e status; ainda sem conversa/GUI completos.

Real-v8 Qwen0.8b local18/18 controladas; duas escritas/impactos, duas incertas,
384 bancos anteriores intactos. Pistas sintéticas, sem captura pessoal/download.
Tentativas v3–v7 preservadas, incluindo erros de polaridade antes das restrições.
185 testes nativos/271,123 s, CI0, três retomadas e192 Python AST/whitespace.
Teste conceitual antigo ajustado para não conter native_feedbacks em formatos40/41.
Retomada também expôs temporário de publicação após cancelamento: limpeza restrita
à pasta UUID e nomes reconhecidos, após processo terminar.12 testes conceituais e
16 de worker/coordenação passaram após correção; CI final0. Logs falhos preservados.
Memória: exemplo abelhas/formigas do usuário exige distinguir familiaridade,
detalhes/reaprendizado/repetição. Retenção episódica atual não prova esquecimento
gradual semântico nem recordação humana; meta ampla continua ativa.

## Alice — valores episódicos por conseqüência e afeto funcional compartilhado (12/10/2026)

NativeAttention2 guarda moment_ref na decisão/fonte; NativeGrounding.learn_attention
prepara valores antes do update de atenção e credita somente episódio retido correto.
MomentValues RLS diagonal(capacidade×3/p/update),81.920 B em2048. Fonte/hash/horário
no trace, resultado nos pesos. Positive/negative magnitude modula retenção em
escala86400 s fornecida, além de frescor300/heat120. Pode esquecer; não é verdade
nem resolve ambiguidade. Crédito único por aquisição; revisão afetiva tardia pendente.
Quiet/episódio esquecido aprende ação/estado, sem novo episódio ou crédito no slot
reutilizado. ConceptualMind atualiza progress/social/valence só com feedback válido.
Moment formats5/6 e atenção2; externos51/52/native7 mantidos. Legacy sem inventar
impacto. Restore valida fonte/episódio/pesos/decisão e recusa meio commit/vínculo errado.
GC suporta6; valor não reescreve páginas sensoriais. Retire desloca/reseta valores.

Onze contratos/10,928 s,175 nativos/285,412 s e CI0;188 Python AST/whitespace.
native-impact-real-v1:120 s em cópias do runtime/context-seed17 e inbox/retention;
quatro escolhas frias image/audio/all/quiet e feedbacks de currículo. Oito sinais
recebidos/quatro atendidos/três episódios valorados204–206; quiet sem episódio.
Valores~0,874913/−0,724928/0,349965, valência funcional~0,133754. Vida207/retidas12,
238 atendidos/246 recebidos, três writes/oito fontes. Nomes/relatos/384 bancos
preservados. Atual/anterior/portátil retoma sem modelo/replay; repouso5 s não treina.
Manifesto native-impact-manifest.json; nenhum novo modelo/sensor ao vivo/autostart.
Não sentimento lido da voz nem apego espontâneo; utilidade/curvas fornecidas. Meta
ampla continua ativa: interação natural, confiança, significados, consolidação/
esquecimento de conhecimento, ações e rotina contínua ainda incompletos.

## Alice — correspondência condicionada pelo working anterior (12/10/2026)

NativeLinks gerais129→128 + seis contextuais265→128; total6.590.400 B. Chave usa
cue128/contexto DCT8/interações DCT16×8/bias, base fixa/versionada. Coeficientes
aprendem; projeção/família fornecidas. NativeGrounding fornece working decaído
anterior à chegada, antes de incluir qualquer alvo atual. associate_native
contextual=True consulta working atual; fora de cobertura se abstém. Erro causal
contextual modula novidade, não hipótese treinando a si mesma. Snapshot links2;
links1 conserva geral e inicia contexto vazio. Externos51/52/native7 mantidos.
Rollback prepara ambos grupos/direções; restore verifica base/counts/covariância.

Cinco contratos:72 consultas reservadas em3 bases, inversão contextual da mesma
pista, controle apagado/contexto desconhecido, primers reais no fluxo sensorial,
checagem de contexto antes do alvo, fonte parcial, migração/rollback/corrupção.
164 testes/288,873 s, cinco específicos/7,597 s e CI0;185 Python AST/whitespace.
native-link-context-files-v1-seed17/29/71: recibos congelados e formas/sons
controlados,24/24 condicionais vs12/24 gerais, apagado0/24 suporte. Nenhum novo
nome/ID de contexto entregue à Alice. Episódios de treino retirados por washout
mono com300 s de tempo simulado;24 alvos reservados só no avaliador. Vida204,
retidas12,234 perceptos atendidos/238 recebidos,188 frames/16 contextuais.
Nomes/relatos/384 bancos antigos preservados por cópia. Três portáteis e duas
gerações paginadas retomadas sem modelo;5 s quiet não escreve. Manifesto
native-link-context-manifest.json. Meta ampla permanece ativa; não demonstra
contexto aberto do cotidiano, subjetividade, fala livre ou esquecimento gradual.

## Alice — correspondência multimodal sem nome e erro no estado compartilhado (12/10/2026)

NativeLinks seis bancos RLS129→128/1.591.392 B; aprende coocorrências atendidas
image/audio/text sem nomes. Família linear, modalidade e sincronia fornecidas.
associate_native devolve cross_modal_expectation, não evento percebido/episódio
nem mídia reconstruída. Covariância/norma são cobertura heurística; relação ambígua
pode gerar média, ainda sem distribuição contextual. Self/hipótese não ensina.
Erro de alvo real é computado antes do update e combinado com erro temporal para
novidade do estado interno compartilhado. Quiet/mono/repouso não escrevem pares.
Externos51/52/native7/links1; legados1–6 inicializam sem replay. Oito contratos
incluem base rotacionada/combinações reservadas, máscaras, pesos apagados/invertidos,
rollback, corrupção, migração, erro causal e integração real do estado interno.

native-links-files-v4-seed17/29/71: recibos de encoder congelado verificados contra
arquivos controlados; não nova inferência nem sensores vivos.36/36 associações
reservadas corretas, pares trocados/apagados0. Todos episódios de treino retirados
por12 exposições mono espaçadas300 s em relógio simulado. Vida40/retidas12,
66 atendidos/70 recebidos; histórico16+24 frames de links,12 writes por direção
image/audio. Nomes/relatos/384 bancos antigos preservados por cópia. Coseno médio
aprendido~0,996–0,997/identidade~0,791–0,796; não demonstra semântica cotidiana.
Três portáteis e duas gerações paginadas retomadas em processo novo sem modelo;
5 s quiet preserva pesos.183 arquivos Python AST/whitespace.
159 testes nativos/271,125 s, oito específicos/9,620 s e CIexit0. Fontes, logs,
relatórios e snapshots finais no native-links-manifest.json; falhas iniciais mantidas.
Meta ampla segue ativa: esquecer detalhes/conhecimento gradualmente, consolidação,
contexto/segmentação/categorias, confiança, curiosidade, diálogo aberto e rotina no PC.

## Alice — retenção limitada com IDs de vida e aprendizagem preservada (12/10/2026)

NativeMoments substitui episódio de menor prioridade ao atingir capacidade2048;
prioridade fornecida, baseada em frescor/novidade/reativação, não significado pessoal.
IDs monotônicos distintos de slots; next_id/total_observations preservam contadores
de vida e treino preditivo. Nomes aprendidos sobrevivem ao episódio de treino.
Relatos/recibos guardam moment_ref (tempo/máscara/hash/fontes sem vetor sensorial)
e nunca apontam ao novo ocupante de um slot. Correções posteriores preservam
linhagem; conteúdo sensorial retirado não é fabricado. Externos51/52/native6,
moments3 portátil/4 páginas, interpretations2/stream2; compatibilidade anterior.
SQL64 MB/páginas128 MB/journal6.144 permite atual/anterior/captura nova; GC próprio
mantém ambas as gerações. Corrigida limpeza de cursor SQLite ao rejeitar archive
corrompido no Windows; rollback preserva episódio anterior quando orçamento falha.

native-retention-real-v1: cópia de runtime/inbox, limite12 somente no ensaio;
16 experiências de vida/12 retidas,0–3 esquecidas. Percepção30 atendidos/34 recebidos,
previsão13 frames/10 pares, relato0 pai→mae mantido com episódio0 ausente.384 bancos,
nomes, duas versões e quatro feedbacks anteriores preservados. Mídia repetida;
não demonstra percepção cotidiana, esquecimento gradual ou personalidade.

Usuário: lembrar100% não é requisito; até conteúdo importante pode ser perdido.
Exemplo abelhas/formigas orienta ensaios futuros de exposição desigual, conhecimento,
familiaridade residual e reaprendizagem. Onze novos contratos. Meta permanece ativa:
consolidação/esquecimento de detalhes e conceitos, importância pessoal, segmentação,
aprendizagem geral e rotina contínua no PC ainda requerem trabalho.

Validação:150 contratos nativos/265,753 s e11 específicos/21,256 s (um teste novo
de ID longo após a bateria); CIexit0. Atual/anterior/portátil retomados em processo
novo sem modelo;180 arquivos Python AST/whitespace verificados. Fontes, relatório,
logs e snapshots no native-retention-manifest.json, artefatos sob bin/AliceMemory.

## Alice — aquisição seletiva e valor de atenção por experiência (12/10/2026)

NativeAttention:681.160 B em5 bancos, ações/cobertura/exploração/utilidade fornecidas;
valores por contexto aprendidos via Consequence externo. Full/learned/quiet,
CLI/API e observer local não persistido. Feedback self/errado não treina nem
invalida percepção. Pending16/60 s, fontes512. NativeGrounding separa recebido/
atendido; só selecionados entram em arquivo/nomes/previsão/reconhecimento.
Watermarks impedem replay dos ignorados; posterior não preenche gap antigo.
Sem nova fila; externos51/52/native5, legacy1–4 migrafull/received=observations.

Bateria157/CI0/14 contratos novos. Real native-attention-real-v1: quatro frames
repetidos, oito sinais recebidos/quatro atendidos/três momentos; image/audio/all/
quiet é exploração fornecida. Quatro conseqüências roteirizadas aprendidas,
escolhas aprendidas demonstradas em outros ensaios controlados. Doze momentos/
22 atendidos/26 recebidos,384 bancos/nomes/duas versões preservados, workers
terminal; tick5 s não inventa feedback. Filtragem após encoder não economiza
inferência. Atenção espacial/intra-canal, interesse geral e descanso escolhido
fora do currículo pendentes. Priorizar lotação2048 para não parar aprendizagem.

## Alice — previsão nativa sem nomes e continuidade em repouso (12/10/2026)

NativeDynamics: próxima modalidade em bancos RLS, contexto/presença/traço temporal,
erro antes do update. Família linear fornecida,8.003.184 B de tensores. Aquisição
governa sequência, continuidade2 s fornecida; self/ausência/previsão não são alvos.
Observe_native comum API/stream liga erro à novidade/carga no FunctionalState.
Externos51/52 mantidos/native4, legacy1–3 sem replay/invenção de treinamento.

Nove contratos/143 bateria/CI0. Rotação reservada antes do alvo em3 seeds,
histórias distintas/contexto anterior, pausa/delay/retomada/migração. Ensaio
native-dynamics-real-v1: seis frames públicos repetidos, cinco pares/update
vision/audio, texto0; erros1,93e-15/2,47e-15. Nove momentos/18 perceptos,384
bancos/nomes/duas versões antigos preservados; intervalo5 s conserva pesos.
Não é generalização cotidiana; atenção/ação/curiosidade/repouso escolhido,
esquecimento/capacidade e desenvolvimento aberto seguem pendentes.

Usuário esclareceu: não-alteração era instrução ao Claude; meta retomada.
Ensino e exploração próprios coexistem. Não otimizar cada instante; quietude
é válida. Visão filosófica orienta projeto. Não exigir100% de lembrança: esquecer
detalhes/familiaridade/reexposição é distinto de corrupção/perda catastrófica.

## Alice — perguntas sobre interpretações e requisitos do aprendizado (12/10/2026)

NativeMeaningQueryLane: nome/pistas aprendidos localizam momento, relação em
pesos fornece initial/current/comparison. Parser pergunta apenas; frases
delimitadas mantêm relato recebido versus percepção. Ambiguidade não resolvida
pela presença da relação. Stale answer reconsultada na expressão/entrega;
restore permite resposta anterior à correção posterior. Sem novas experiências.
Mesmo worker/clock, quatro jobs, CLI question-mode meaning/status. Snapshots
51 portátil/52 paginado/native3, migra40–50; loader/coleta reconhecem52.

Qwen0.8 real: cinco perguntas em cópia native-meaning-query-real-v1, ambiguidade,
initial pai/current mae/comparação, relação desconhecida sem sujeito. Três
momentos/seis perceptos/duas versões e bancos antigos preservados. Nove contratos
específicos e bateria133 passam/CI0; host finito encerrado, modelos preservados.
Não é conversa livre nem inferência de autoria verdadeira da foto/voz.

Usuário: aprender não depende de conhecer o ato de aprender; metacognição pode
vir depois. Nova informação não implica verdade. Atenção afeta aquisição, não
só prioridade posterior. Confiar/investigar pode decorrer de personalidade e
experiências, sem checagem deliberada obrigatória de cada informação. Plano
atualizado; mecanismos aprendidos de atenção/confiança ainda não demonstrados.

## Alice — interpretação relatada e correção preservando o passado (12/10/2026)

NativeInterpretations: relações/sujeitos genéricos em pesos RLS de endereços de
versão. Até4096 versões/32 relações/64 sujeitos, 2.129.920 B de tensores residentes;
save ainda copia esse banco. Registries nomeiam símbolos, provenance sem sujeito.
Initial primeiro relato; current versões ativas. Conflito sem correção permanece;
correção nomeia versões ativas mesmo momento/relação e preserva pesos antigos.
Fonte posterior tem horário próprio. Self/stale/cross-momento/lotação recusados.
Reported interpretation/directly_observed=false; não reescreve percepções.

NativeStatementLane: declarações literais em português, parser sem histórico,
validação de campos/negação; quatro jobs/shared slot, prioridade de ensino antes
da consulta, TTL/cancel/deferral/restart. CLI native-statement-file. Consulta API
native.interpret(moment,relation,view), expressão aberta ainda pendente.
49 portátil/50 paginado/native3; 40–48/native1–2 migrados sem inventar crenças.
Loader/coleta reconhecem50, fila e learning source vinculados à declaração.

Real native-meaning-real-v1: Qwen0.8/host próprio finito, palavras curriculares
pai→mae; current muda, initial pai preservado. Negação uncertain/sem update;
duas versões, três momentos/seis perceptos e 384 bancos antigos preservados.
Não afirma autoria real das mídias públicas nem reconhecimento de família.
18 testes novos +131 regressões, CI0, 169 Python AST/whitespace, sem discovery.
Manifesto bin/AliceMemory/native-meaning-manifest.json. Meta ativa: inferência
própria, identificação conversacional do acontecimento, revisão de deduções,
conversa aberta e demais capacidades fundamentais permanecem.

## Alice — pergunta nativa liga português à evocação em pesos (12/10/2026)

NativeQueryLane no mesmo proprietário/slot consulta nomes→pistas e momentos em
pesos. Parser recebe só pergunta literal: nome entre aspas, pistas de modalidade,
janela [início; fim] relativa/UTC explícita. Sem pistas escritas, primeira aprendida
em ordem fixa; não escolher pelo resultado. Ambiguidade permanece. Consulta não
escreve perceptos/nomes; restore/validação não reativam. Frases autorizadas verificadas
no texto real; fidelidade à evidência, confiança não calibrada, sem diálogo aberto/
descrição de cena/voz/persona avaliados. Alteração de pesos/arquivo invalida expressão
antes de entrega; reconsulta. Quatro jobs, TTL/cancel/deferral, prioridade interativa.

47 portátil/48 paginado conservam fila; 40–46 migrados, filas legadas vazias.
Página/coleta reconhecem48. CLI question-mode native. native_query_probe copia
runtime/inbox com leases, preserva UUID/counters/fontes e permite resume limitado
de baseline falhado. Schema variants ligam uncertain aos campos literais.

Real native-query-real-v1: primeira proposta omitiu imagem, recusada/preservada;
diagnóstico/esquema corrigidos, mesma cópia retomada. Qwen0.8 privado/finito90%,
seis perceptos/três momentos/uma aula maruvi, arquivos públicos repetidos. Antes,
sem associação; depois, três candidatos; janela evoca momento0 anterior à aula
em imagem/áudio; fenvori desconhecido não ganha significado. Não é português
falado geral nem generalização de sinais. Manifests/host preservados/terminais.
14 testes novos +117 regressões, CI final0, 163 Python AST/whitespace, sem discovery.
Manifesto bin/AliceMemory/native-query-manifest.json. Meta ativa: conversa aberta,
interpretação revisável, demais fundamentos/aprendizado geral permanecem.

## Alice — coleta conservadora de páginas órfãs nativas (12/10/2026)

`native_page_gc`/owned.json registra SHA/tamanho antes da escrita; legado registrado
somente quando verificado/usado. Até4096 entradas/512.000 B. Writer/lease único,
antes da admissão e após commit/limpeza da geração expirada. Protege current/previous
publicados no disco e captura em andamento; API manual recusa writer ocupado.
Sem candidatos evita carregar checkpoints. Metadados do registro validados sem
varrer caminhos no núcleo. Checkpoint46/portátil45 e orçamentos continuam iguais.

Antes de remover: hashes/tamanhos das gerações, referências e bancos retidos válidos.
Qualquer .pt extra suspende coleta. Remove somente banco próprio registrado, sem
referência, hash/tamanho/fatores válidos, path resolvido dentro do arquivo próprio.
Preserva desconhecido/alterado/não-banco. Página exclusiva de previous só sai após
expirar das duas gerações. Intenções sem arquivo conciliadas se não protegidas.
Delete/journal interrompidos retomáveis; limpeza parcial/skipped reportada em
native_page_gc.before/after sem invalidar um commit já publicado. Dados incertos
podem continuar consumindo espaço; não apagá-los para forçar admissão.

`native-gc-real-v1`: 259 momentos, coleta16 páginas/274.752 B, página sem registro
e texto alheio intactos. Novo momento grava um banco/17.172 B. Current/previous/
portátil restaurados em processo novo, cache0→4, consultas incluem último momento.
384 bancos/observações anteriores preservados, sem modelos. Capturas38,458/22,323/
40,477 ms; writer4,045/0,573/1,669 s (último inclui coleta), peak246.956.032 B.
13 testes novos +55 regressões, CI final0, 159 Python AST/whitespace, sem discovery.
Manifesto: bin/AliceMemory/native-page-gc-manifest.json. Meta ativa: demais bancos
incrementais, escala maior e capacidades fundamentais/conversa continuam pendentes.

## Alice — bancos nativos incrementais e checkpoint 46 (12/10/2026)

RuntimeStore.capture no ConceptualMind destaca só bancos novos, estado congelado
e referências a páginas SHA-256 imutáveis no diretório irmão native-pages. Páginas
gravadas/fsync/verificadas antes do current/previous. Índice limitado evita varrer
caminhos no núcleo; writer verifica hash de cada referência. Após falha, ressincroniza
índice e reutiliza páginas já completas. Não apaga órfãos/arquivos estranhos; limite
64 MB e 4096 entradas no índice, até 2048 momentos referenciados. GC pendente.

Checkpoint 46 depende da pasta completa; copiar/mover após fechar proprietário.
Leitor vinculado pelo loader, limitado em bytes/path/ownership/hash, valida e copia
um banco por vez para SQLite temporário; cache inicial zero/até quatro. Página
nova exclusiva corrompida permite previous; compartilhada ausente invalida ambas.
Página com hash válido mas conteúdo inválido também faz fallback. Runtime aceita
UnpicklingError na recuperação, sem enfraquecer validação. Exportação portátil
continua formato45/autocontida. Formatos anteriores aceitos; record do commit intacto.
Evento de persistência reporta páginas/referências/bytes; fila nativa usa mesmo
commit duplo antes de liberar sinais.

Real proprietário anterior + 256 frames sintéticos + um: 258→259 momentos.
Primeiro salva 257 páginas únicas/4.413.204 B; sem aprender, zero páginas novas;
um frame novo, uma página/17.172 B. Checkpoint12.861.544 B vs portátil17.355.046 B.
Captura índice37,002/20,937/37,735 ms; primeira versão353–403 ms, evidência preservada.
Commit separado3,660/0,577/0,541 s; hashes ainda lineares. Pico processo246.546.432 B,
sem modelos. Current/previous/exportação consultados em processo novo, 384 bancos
antigos preservados. 16 testes novos + 77 regressões; gates finais/manifesto
`bin/AliceMemory/native-page-store-manifest.json`. Meta ativa; GC, escalabilidade,
demais bancos incrementais e desenvolvimento aberto continuam pendentes.

## Alice — momentos sem nomes e bancos nativos no SSD (12/10/2026)

`NativeMoments` no proprietário guarda um momento por frame externo, sem exigir
nome/aula. Associação entre modalidades em fatores RLS de posto até três, equivalentes
ao cálculo denso. 15.552 B de tensores/banco versus 544.896 B densos; bancos em
SQLite próprio com hash, cache de quatro e índice residente. Recorte até 2048
momentos/64 MB, sem apagar passado ao lotar. Snapshot exporta arquivo completo;
SQLite de trabalho temporário reconstruído na retomada. Persistência incremental
e índice escalável continuam pendentes. Checkpoint 45/native2, migração 40–44
não inventa episódios a partir dos nomes antigos.

Consulta multimodal com janela relativa/UTC. Candidatos indistinguíveis se abstêm;
prioridade não resolve ambiguidade. Evocar mantém presente e não escreve outro
episódio. Captura, ingresso UTC e processamento distintos. Importância por novidade
é política fornecida, separada de frescor/reativação, sem importância afetiva aprendida.
Frame fornecido, sem fronteiras aprendidas. Worker sensorial sequencial image/text→audio
libera encoder entre fases; comparação com completo: zero diferença em duas entradas,
CPU/BF16. Picos do processo 1,769/2,106 GB, sem ensaio de VRAM/execução direta do SSD.

Real `native-moments-real-v1`: dois frames iguais foto/fala em tempos diferentes,
4 perceptos/2 momentos/0 nomes/0 aulas. 90 s inicialmente adiados por RAM; retomada
120 s concluiu mesma fila após gap 7795,778 s, sem inputs inventados. Auditoria das
duas gerações: 384 bancos antigos e demais pesos preservados. Processo novo sem
modelos consulta via peso de endereço: ambíguo sem tempo, correto com UTC. Controle
de saída apagada no cache se abstém; páginas originais não alteradas.

256 momentos sintéticos: SQLite 4.464.640 B; cache quatro bancos/62.208 B de tensores,
índice 6.291.456 B, checkpoint 10.849.624 B. Exclui overhead/modelos/SO. 16 consultas
repetidas em processo novo; medianas frio/cache 3,657/3,069 ms com cache do SO intacto.
15 testes novos + 73 regressões + repetição final dos 14 testes de stream. CI final
exit 0 fora do sandbox; restrito falhou por socket. 155 Python AST/whitespace, sem
discovery global. `bin/AliceMemory/native-moments-manifest.json` registra evidências.
Default75/override90 somente finito. Meta ativa; revisão episódica nativa, segmentação,
conversa grounded, captura ao vivo, curiosidade e metacognição ainda pendentes.

## Alice — inbox ativa e retomada de percepções persistidas (12/10/2026)

`NativeInbox` publica cópias atômicas de arquivos locais; `NativeStream` mantém
quatro jobs no proprietário, fonte/contador, últimas 16 entregas. `NativeProcess`
finito compartilha o slot de inferência, isolado do núcleo; ticks prosseguem.
Modelo não recebe nome ensinado. Receipts checam origem/hash/tempo/norma/modalidade.
Source UTC e received UTC separados; tempo relativo antes da origem do relógio
é limitado a zero com absoluto preservado. Frames capturados não expiram offline/
esperando RAM. Worker tem deadline de 240 s. Checkpoint 44/compat 40–43 preserva
pendentes/concluídos. Dois commits com frame terminal protegem fallback antes de
liberar cópias; erros/limpeza parcial não apagam originais nem arquivos estranhos.
Receipts compactos crescem no disco; arquivo autobiográfico nativo ainda pendente.

Runtime `--native-inbox`, `--native-models`, `--native-interpreter`; publisher
`scripts.alice_memory.send_native_frame`. Opt-in, sem captura/autostart instalados.
Default 75% RAM; acima disso somente duração finita/override experimental autorizado.
Não transformar a autorização temporária de 90% em configuração permanente.

Real `native-stream-real-v1`: amostras oficiais de foto/fala em inglês, origem do
falante não verificada, alias externo `maruvi`. 4 frames/6 perceptos/2 aulas, foto,
áudio e palavra escrita; envios sem aula reconheceram memória ensinada. Repetição
dos mesmos sinais, sem novo ensaio de generalização/Português/voz do usuário.
35 s terminou incompleto com 3 pendentes; 75 s retomou o mesmo estado e completou
sem reenviar. Gap 202,496 s sem inputs inventados. 341+748 ticks/36+76 commits.
Processamento sensorial lento, sem alegar tempo real pela cadência de ticks.
384 bancos e demais pesos antigos intactos em ambas as gerações; auditoria fresca
sem modelo evoca imagem/áudio/texto aprendidos. Cópias liberadas/originais intactos.

14 testes novos + 59 regressões, CI exit 0, 152 Python AST/whitespace; sem discovery
global novo. `bin/AliceMemory/native-stream-manifest.json` registra auditoria/falhas.
Meta ampla ativa; episódios nativos, conversa grounded, percepção/captura real
mais ampla, curiosidade, metacognição, capacidade e integração UI permanecem.

## Alice — encoder nativo e associação em pesos no mesmo proprietário (12/10/2026)

EmbeddingGemma 2 revisão fixa baixada/verificada, 1.525.808.822 B no SSD experimental.
Torch 2.10 CPU/Transformers 5.19/Sentence Transformers 6.1 em venv separada; global
Torch 2.4.1 e modelos Ollama preservados. Pixel/PCM/texto diretos, sem legenda/ASR.
`NativeEncoder` offline/BF16/128 dimensões/70 tokens visuais; `NativeBatch` processo
finito com RAM monitorada, receipt/token/hash/proveniência/tensor validados. Núcleo
continua dando ticks. Smoke v1 sem template falhou; arquivo oficial verificado
completou o carregamento. Primeiro núcleo em Torch 2.10 falhou na projeção antiga;
separar o worker mantendo o núcleo 2.4.1 resolveu, sem afrouxar esse verificador.

`NativeGrounding`/checkpoint 43 no `ConceptualMind`: nomes externos sincronizados
ensinam RLS de leitura/evocação, nome reconhecido visualmente evoca áudio e vice-versa.
Sem tabela de significados/exemplos; registry somente nomes/fontes. Tempo compartilhado,
transação por frame, origem/versionamento, self/stale recusados, working state com
decaimento, restauração 40/41/42 compatível. Não interpretar embeddings reais com
o classificador sintético anterior. Conceitos afins e esse léxico ainda têm ligações
abertas pendentes; não afirmar percepção real geral/metacognição. Runtime retoma e
reporta estado nativo; inbox/sensores e conversa desses significados ainda pendentes.

Trials `native-grounding-real-v2-seed17/29/71`: mídia gerada em arquivos PNG/WAV,
3 classes, 4 variantes ensinadas/2 reservadas. 36/36 nomes, 36/36 evocações cruzadas;
sem ensino/apagar/trocar pesos 0/36. Min cosine por seed .992729/.995304/.993804.
12 aulas/24 perceptos por seed. Auditoria fresca sem encoder/LLM/arquivos de sinal
reconhece 36; 1152 bancos antigos e demais pesos intactos. 36,813/38,219/38,422 s.
Pico worker ~2,385 GB; pico PC 28,164/27,865/27,601 GB; CPU-only/override autorizado
90%, padrão 75% preservado. Nenhuma câmera/microfone/histórico privado usado.

13 testes nativos + 46 regressões e CI final exit 0; sem discovery global novo.
Auditoria: `bin/AliceMemory/native-grounding-manifest.json`. Meta ampla ativa.

## Alice — consulta conceitual em português sem repetir a aula (12/10/2026)

`ConceptQueryLane` compartilha o slot de linguagem do proprietário existente.
Pergunta literal com conceitos entre aspas/vetor → parser pré-treinado → dedução
nos pesos → expressão pré-treinada. Aulas/definições anteriores não entram no
parser. Schema vincula nomes/vetor à mensagem; interpretação incerta se abstém.
Composição segue ordem explicitamente escrita, recorte declarado. Vetor da frase
é validado inclusive em colchetes/decimal português; não certificar prosa geral.
Premissa alterada durante expressão/antes de `take_concept_answer` exige nova
consulta. Consulta não modifica pesos/episódios. Checkpoint 42/fila limitada guarda
parser/expressão pendente e respostas até entrega; 40/41 compatíveis. Runtime aceita
`--question-mode concept`, reporta evidência/verificação numérica separada.

Real `concept-query-real-v4`, Qwen 0.8B: 3 vetores reservados, erro máximo .000300,
1 conceito desconhecido recusado. Sem reapresentar as 3 aulas do checkpoint.
Pesos apagados/saídas trocadas erram todas as consultas. 400 ticks/23,625 s; 384
bancos antigos, pesos conceituais/fontes, semânticos/lexicais/importância intactos.
Retomada independente sem modelo entrega respostas idênticas. Texto mecânico:
`numeric_text_verified` true, `free_text_semantics_verified` false. CPU-only,
pico de RAM do PC inteiro 28.579.098.624 B. V1/V2 falhos preservados; V3 cancelou
ao cruzar 90% durante testes concorrentes; V4 passou após liberar essa concorrência.
Hosts próprios encerrados, catálogo existente preservado, teto não aumentado.

12 testes novos + 64 regressões; CI final exit 0; 137 Python AST/whitespace.
Sem novo discovery global. Auditoria em `bin/AliceMemory/concept-query-manifest.json`.
Plano atualizado; meta ampla ativa. Consulta/ensino abertos, metacognição aprendida,
iniciativa, áudio/visão reais, conversa de qualidade e integração permanecem.

## Alice — português pré-treinado e ensino persistente real (11–12/10/2026)

`ConceptLanguage` interpreta aulas literais em português, `TeachingLane` valida
e aplica `ConceptLesson` ao núcleo. Mesma reserva de worker da conversa; fila 4,
deadline/deferral/cancelamento. Checkpoint 41 conserva aula pendente/concluída sem
repetir commit ao retomar; 40 aceito. CLI aceita aula em arquivo e seleção de
modelo/endpoint somente com filas vazias. Deduções próprias não são aula externa.

Usuário autorizou **90% de RAM para teste temporário**, com monitoramento/cancelamento;
não perguntar novamente para esse escopo. Padrão 75% e configurações pessoais
preservados. CPU-only; guard de GPU anterior preservado. Usuário orientou uso conjunto
de RAM/VRAM/disco. Episódios já paginados; ampliar tiers/cache e medir limites por
componente. Não alegar execução eficiente da LLM no SSD: não avaliada.

Real `qwen3.5:0.8b-q8_0`: 3 aulas/3 atualizações; entrada nova (.3,.7) retorna
(.599940,2.099790), erro .000210. 384 bancos antigos e observações preservados,
419 ticks/24,67 s. Pico 28.496.756.736 bytes é RAM do PC inteiro. Negação simples
interpretada positivamente pela LLM foi bloqueada pelo verificador. Retomada
reproduziu aprendizado sem carregar modelo/passado. Artefatos `teaching-real-v1`.

Conversa/visão: cinco amostras em `small-language-evaluation-v4`; resposta casual
pertinente, desconhecimento de música preservado, formas/cores em uma imagem,
frase sobre aprender ruim. Expressão de hipótese falhou por chaves erradas; schema
agora fixa atributos/valores presentes na hipótese. Controle v2 aceito; ainda não
valida conteúdo livre. Runtime real V1 classificou quem como atividade, V2 omitiu
nome. Guia de expectativas e nomes presos ao input corrigiram metadados: V3–V5
`autor=usuario` do kernel. Expressor agora recebe hipótese/tarefa, sem aliases crus
da pergunta; pergunta original preservada no dono. V5 299 ticks/7 commits/30,13 s,
384 episódios intactos. Texto livre permanece genérico/inadequado; não considerar
linguagem livre aprovada ou personalidade avaliada. Falhas antigas preservadas.

121 contratos direcionados distintos cobertos pelos lotes de ensino/core/filas/
orçamento/entrada/expressão; sem novo discovery global. Protocolo e logs em
`ALICE_NEURAL_MEMORY.md`. CI final exit 0, 132 fontes AST/whitespace verificadas.
Auditoria de bancos/valores antigos e retomada sem LLM no manifesto
`bin/AliceMemory/real-teaching-manifest.json`. Meta ampla continua ativa: faltam conceitos abertos,
percepção real, conversação acoplada de qualidade, iniciativa geral e integração.

## Alice — ensino abstrato e investigação integrada (11/10/2026)

`concept_memory.py` aprende transformações afins 2D em RLS a partir de aulas
externas; consulta/composição usa pesos. Proveniência distingue ensinado/testado
de deduzido. Versões de premissas superam hipóteses dependentes após aprendizado;
verificação confirma só um exemplo, sem ensinar a própria previsão. `ConceptualMind`
integra isso ao relógio, percepções e fila existentes. Checkpoint 40 inclui perguntas
emitidas até entrega explícita; scheduler e persistência reconhecem o formato.

Seeds 17/29/71: 14 aulas por seed, 192/192 problemas reservados corretos (96
operações/96 composições não ensinadas). Sem ensino 0/192; mesmas quatro consultas
fixas 52/192; pesos apagados 0/192; pesos trocados 1/192. Covariância/custo escolhem
entrada informativa entre opções do ambiente. Retomada reproduziu consulta,
investigação, relógio e estado temporal; 1152 bancos anteriores e observações
preservados. Não demonstra descoberta da composição, conceitos abertos, curiosidade
geral, conceito de aprender ou aula em português. Família afim/composição são
fornecidas; transformações aprendidas. Ainda sem inferência do candidato 0.8B.

37 testes direcionados OK (11 conceitos + 10 store + 1 cena + 15 fila neural),
CI geral exit 0; nenhum novo discovery completo. Artefatos `conceptual-v1-seed*`
e logs `test-concepts-runtime-verified.log`, `test-concepts-neural-regression.log`,
`ci-concepts.log`, sob `bin/AliceMemory`. Plano e limites em
`ALICE_DEVELOPMENT_PLAN.md`/`ALICE_NEURAL_MEMORY.md`. Meta ampla permanece ativa.

Ao responder sobre estágio/diferenciação: protótipo de pesquisa integrado; ainda
inicial para convivência real. Comparação primária com Hindsight, Titans, Voyager
e Qwen3-Omni registrada no plano. Continuidade/memória neural/aprendizado online
já têm precedentes; combinação e objetivo pessoal são direção, não inovação
científica ou superioridade demonstrada. Faltam avaliação comum, percepção real,
linguagem natural de ensino e investigação geral.

## Alice — persistência assíncrona e fundamentos conceituais (11/10/2026)

Runtime experimental: snapshots destacados, escritor único de disco, lock do SO,
geração atual/anterior com hash e recuperação. Diretório dedicado recusa arquivos
alheios. Captura no thread do núcleo; perda de mudanças não comprometidas em queda
continua possível. Scheduler reconhece checkpoint de cena e serializer da fila
neural foi extraído sem alterar formato. Execuções finitas de 12 s e retomada 8 s
preservaram 384 episódios/observações e expectativa concluída, sem novas percepções.
Lacuna offline 381,61 s; workers encerrados na parada normal. Ainda faltam limpeza
de workers após queda, sensores reais/autostart, inbox geral e integração Xennex.

26 testes direcionados OK (10 store, 15 fila neural, 1 cena), CI geral exit 0.
Sem novo discovery completo. Evidência em `bin/AliceMemory/runtime-v3-seed17`
e logs finais de runtime. Não promover M1/M10 a completos.

Download autorizado do candidato menor `qwen3.5:0.8b-q8_0`: 1.019.201.423 bytes,
manifests antigos preservados. Avaliação adiada pela margem de RAM; zero inferências
do candidato. Contador de uso de VRAM indisponível, sem offload real verificado.

Direção do usuário: companheira com linguagem/percepção inicial pequena e aprendizado
contínuo; fundamentos antes de jogos. Conhecimento também vem de ensino, leitura
e combinação de conceitos. Plano exige distinguir percebido/ensinado/deduzido,
premissas, hipótese e revisão, controles antes/depois e transferência após retomada.
Curiosidade geral e conceito aprendido de aprender ainda pendentes. Não confundir
explicação herdada da LLM com aquisição no núcleo. Plano conceitual detalhado em
`ALICE_DEVELOPMENT_PLAN.md`, protocolo atual em `ALICE_NEURAL_MEMORY.md`.

## Alice — crescimento coordenado e aprendizado durante linguagem (11/10/2026)

`memory_capacity.py` e `GroundedMind.expand_capacity`: arquivo paginado, ledger
neural e importância diagonal crescem juntos após preparar todas as alocações.
Falhas não publicam expansão parcial; limite 4096, sem compressão/arquivo infinito.
Capacidade 321→385 adiciona 40.448 bytes de índices/ledger/valor, sem recriar pesos.

Ensaio `learning_language_experiment.py`, seeds 17/29/71: 192 episódios novos,
384 percepções completas, atualização de regularidade no contexto 0 em pesos
neurais; 960 fontes antigas preservadas. Consultas sensoriais reservadas: 24/24
na regra modificada e 72/72 nas regras mantidas. Categorias/nomes já conhecidos;
tempo sintético acelerado, sem afirmar cadência real ou novas categorias.

Piloto v3 encontrou esgotamento de tentativas em dois pedidos durante aprendizado.
Fila agora aguarda consolidação pendente antes da expressão, preserva prazo,
checkpoint e andamento de consultas factuais. V5 aguarda entrega do pedido
original e da consulta final: ambos atualizados nas três seeds. Retomada em
processo novo após fechar SQLite original reproduz próximo tick/estado/resposta.
Expressor de teste: qualidade/influência da LLM real seguem pendentes. Preflight
21:55 UTC: 25.249.542.144 bytes de RAM usados, acima do orçamento antes da reserva.
Não houve inferência, download, sensores reais ou alterações em dados pessoais.

V5: 27/23/23 frames com worker vivo, espera por aprendizado nos demais. O pedido
original precisou de uma reformulação por seed e foi entregue corretamente;
V4 terminava antes dessa entrega, por isso o runner passou a aguardar os dois.
Gate: 76 testes direcionados OK (6+19+21+15+15), CI geral exit 0.
Auditoria dos checkpoints confirma 960 bancos antigos e valores duradouros/léxico
intactos, 192 episódios novos, 96 consultas reservadas e nove respostas validadas.
Retomada do próximo tick/estado em processo novo conferida. Manifesto
`bin/AliceMemory/learning-language-manifest.json`; 120 fontes Python com AST/whitespace
verificados. Discovery completo anterior 369 é histórico, sem novo discovery global.

## Alice — expectativas na fila e nos slots neurais (11/10/2026)

Modo de expectativa no `LanguageCoordinator` e `NeuralLanguageCoordinator`,
estágio tipado no worker CPU/GPU e contrato leve sem Torch. Mesma fila limitada,
um processo por vez. Slots neurais decodificados consultam os pesos semânticos
sem reler nomes. Afirmações factuais da expectativa devem permanecer vazias;
resultado passa por validação no proprietário do núcleo.

Mudança de conclusão/perda de suporte causa nova geração (até duas tentativas).
Conclusão ainda sustentada conserva proposta com proveniência original e ganha
validação atual separada, mesmo após mudança de pesos/confiança. Conferência
repetida em `take`. Checkpoint 39 para filas mistas; filas factuais continuam 30;
31 aceita base 39. Migração não altera payload; scheduler/leitores reconhecem 39.
Extração de evidências fecha páginas temporárias em sucesso/falha.

Três seeds: 360 ticks em 12 s por seed, 94/96/95 ticks com worker vivo, 21
percepções parciais, 9/9 respostas estruturadas (seis expectativas/três lembranças),
960 fatos anteriores preservados. Kernel/léxico intactos; novo episódio incompleto
usa categorias conhecidas, sem aprender regra nova. Retomada em processo novo
reproduziu próximo tick/estado temporal e expectativa nas três seeds. Artefatos
`expectation-loop-v1-seed*`. Parser/expressor de teste com atraso explícito; não
qualidade linguística real. P95 iteração 15,99/33,29/47,96 ms; P99 atraso de até
249,92 ms: há cauda de atraso, sem causa isolada.

Probe `-Source expectation-loop` usa modelo instalado explicitamente, exige
checkpoint/modelo de intenção, preserva GPU/admissão e servidor próprio temporário.
Preflight atualizado: 24.033.583.104 bytes usados + reserva 4.505.915.124,75 excedem
75% de 33.461.567.488. Nenhuma inferência/modelo carregado. Novas regras/conceitos
durante fala, qualidade real, cauda de atraso e fontes/daemon continuam pendentes.

Discovery: 369 testes /396,117 s OK. Um contrato adicional de leitura/extração
foi incluído depois do início; suíte direcionada final 13 testes /41,540 s OK
cobre a diferença (370 contratos atuais, sem discovery completo de 370).
Auditoria confirmou pesos/precisão/contadores dos 960 bancos episódicos anteriores
iguais aos originais, nove propostas validadas e três retomadas equivalentes.
CI geral exit 0 (`ci-expectation-async-verified.log` e `.exit.txt`). Manifesto:
`bin/AliceMemory/expectation-async-manifest.json`.

## Alice — expectativas neurais expressas separadamente de fatos (11/10/2026)

`GroundedMind.expect_names`, ponte `expectation_language.py` e ensaio finito
`expectation_experiment.py`: nomes aprendidos consultam o mesmo backend semântico,
com expectativas em campo próprio e afirmações factuais vazias. Contrato validado
no adaptador e na entrega. Estado aprendido/progresso das fontes e testemunhas
verificados novamente; revisão durante a geração recusa resposta antiga. Nada
gerado é consolidado como episódio. Confiança não calibrada e texto livre não
verificado. Não é varredura forense de toda página fria por consulta.

Três seeds: 48/48 nomes associados a sinais crus, 96/96 expectativas estruturadas,
960 fatos anteriores preservados, pesos/sampler semânticos intactos, três retomadas
em processo novo reproduzem consulta testada sem SQLite original. Parser/expressor
de teste não avaliam qualidade linguística. Artefatos `expectation-language-v3-seed*`.
Currículo lexical em lote, não encontros reais. Tempo total 13,49/14,69/14,11 s;
consultas com backend de teste: mediana 37,34 ms, máximo 60,91 ms.

Probe `-Source expectation -Question ...` usa instância Ollama temporária já
prevista, com pergunta por arquivo UTF-8. Preflight da guarda de 75% recusou a
reserva: 24.818.962.432 bytes usados + 4.505.915.124,75 estimados em 33.461.567.488
totais. Nenhum modelo carregado/inferência tentada. Falta ligar expectativas à fila
assíncrona e medir texto/modelo real; M0–M10 continuam ativos. Não houve download,
sensores abertos, instalação, alteração de Data/, commit ou empacotamento.

Gate: discovery **353 testes/353,575 s**, 12 contratos direcionados na versão final
(incluindo o novo leitor de arquivo), CI final código 0, sintaxe e guarda de entrada
PowerShell verificadas. Auditoria reabriu checkpoints e recalculou as 96 consultas,
comparando kernel/sampler e os 960 fatos com fontes originais. Manifesto
`expectation-language-manifest.json`, logs `test-expectation-full.log`,
`test-expectation-language-final.log`, `ci-expectation-language-final.log` e
`audit-expectation-language.log`, em `bin/AliceMemory`. Próximo: ligar o modo de
expectativa à fila assíncrona sem converter a hipótese em experiência percebida.

## Alice — projeção de pistas por função neural aprendida (11/10/2026)

Backend opcional `neural-projected`/`neural-v2`: `SupportProjection` compara
outputs do kernel em pistas que variam num campo e conservam os outros dois.
Não recebe campo irrelevante ou alvos para decidir máscara; exige cobertura,
outputs confiantes e baixa influência em um campo/alta nos outros. Descarta no
máximo um campo. Regra estatística/thresholds fixos, não gate meta-treinado ou
prova causal. Consulta compara duas variantes ensinadas, com no máximo duas
testemunhas por digest; resposta vem do kernel, sem ler alvos das testemunhas.
Ausência/ruído no campo descartado tolerados; campos retidos insuficientes se
abstêm. Revisões/fontes pendentes conservam invalidação do v1. Projeção participa
de transação e snapshot, recalculada na restauração para rejeitar máscara plantada.

Três seeds ×32 imagens/sons reservados: **96/96 hipóteses suportadas corretas**
contra 0/96 suportadas no v1 (top-1 bruto do kernel 95/96). Encoder conhece as
categorias; generalização é de novos valores de um campo de baixa influência
em combinações já conhecidas dos outros. Preserva 960 pares episódicos por SHA;
anexo não altera kernel. Nova experiência/consolidação/tick em processo novo sem
SQLite original reproduz checkpoint completo. Pai/filho com uma thread de CPU.
Runners `projected-semantic-v1-seed17/29/71`, ~10,8 s/pai; RSS do filho excluído.
Dez contratos: três papéis permutados após gradientes reais (48/48 codificados),
três campos influentes, pouca cobertura, dados ambíguos/ausentes, duas fontes,
pesos apagados, rollback, leitura pura e adulteração. Factory/cenas usam mesma
fonte/relógio, backends anteriores legíveis e condicional continua padrão.

Gate: **342 testes /332,325 s OK**, CI obrigatório exit 0. Logs
`test-projected-semantic-full.log` e `ci-projected-semantic.log`; novo manifesto
vincula fontes/checkpoints/resultados. Meta integral ativa. Calibração geral,
combinações novas dos campos retidos, dependências seletivas, decisões, sensores
reais e demais lacunas continuam no plano; personalidade segue adiada.

## Alice — backend neural acoplado e revisão de dependências (11/10/2026)

`ConsolidatingMind(..., semantic_backend="neural")` liga kernel 36/índice 38 ao
mesmo banco episódico/relógio, incluindo cenas e wrappers de linguagem. Arquitetura
semântica `neural-v1` é opcional; condicional continua padrão. Envelopes anteriores
23/28/29/35 preservados. Ledger registra revisão, observações, tempo e fingerprints
da interpretação inicial/atual; não guarda alvos. Repetição não reaprende a fonte;
mudanças observacionais e revisões são detectadas, inclusive no mesmo timestamp.

Fontes completas ainda não aprendidas e fontes antigas alteradas suspendem
hipóteses. Invalidar tudo é conservador; grafo de dependências seletivas pendente.
Fonte incompleta não inventa alvo. Índice verifica uma testemunha por digest;
resposta vem do kernel. Suporte exige três pistas e combinação já observada,
com confiança/margem heurísticas não calibradas. Hipótese nunca vira fato por
simples leitura. Usar consolidação do episódio atual regularmente nesse backend.
Kernel/rotas/sampler/ledger e lote semântico da cena são transacionais; falha de
fonte adia consolidação e conserva o frame confirmado. Restauração de checkpoint
inválido libera o arquivo paginado criado. Revisão pendente persiste sem apagar
rotas antigas; continuidade em processo novo foi medida com uma thread de CPU.

`neural-semantic-v1-seed17/29/71`: 320 encontros/640 frames por seed passam agora
pelo mind. Stream, pesos finais de kernel/índice e sampler coincidem com o ensaio
isolado; mantém 47/48 novas e antigas, 24/24 regras modificadas e 960/960 fatos.
96/96 hipóteses corretas nas pistas ensinadas dos representantes. Combinações
reservadas: abstenção completa; acerto bruto de top-1 não é suporte calibrado.
58.712 B de tensors semânticos +5.056 B do sampler, capacidade 321; fonte,
percepção, temporal e overhead não incluídos. Runners ~42–44 s, RSS/pico em
relatório. Consulta após apagar contexto recente continua igual.

Gate final: **330 testes /326,113 s OK**, 75 direcionados OK, CI obrigatório exit 0.
Logs em `bin/AliceMemory`: `test-neural-semantic-final-full.log`,
`test-neural-semantic-integration-current.log`, `ci-neural-semantic.log`.
`neural-semantic-manifest.json` vincula fontes, relatórios e checkpoints; gerador
reconfere 960 fatos salvos, pontuações e 96 hipóteses observadas. Hindsight segue
referência de organização/proveniência, sem instalação/código externo copiado.
Meta inteira permanece ativa. Próximo: suporte aprendido para combinações novas,
calibração, dependências seletivas e expectativas nas decisões; os demais marcos
e personalidade adiada permanecem no plano.

## Alice — retenção/plasticidade por reativação neural (11/10/2026)

Kernel protegido 37, índice de reativação 38 e ciclo atômico de consolidação:
seleção de até três representantes anteriores por pistas aprendidas, recuperando
valores dos pesos originais. Índice não guarda alvo; mantém ID/revisão, tempo,
digest e chave. Atualiza representante sem apagar fatos; mudança de pista remove
rota antiga e mantém checkpoint válido. Fonte alterada é ignorada até refresh.
Falha no segundo write/orçamento restaura kernel, proteção, rotas e RNG. Ciclos
podem deliberadamente reaprender; ledger/scheduler exatamente uma vez pendentes.

Mesmo currículo/pares SHA-256 do ensaio anterior, três seeds ×320 encontros.
Representantes3: 47/48 novas e 47/48 antigas após segundo lote (antes 28/48 antigas);
24/24 regra modificada e 71/72 antigas inalteradas ao final; 960/960 fatos intactos.
Limiar anterior >=90% em cada fase/seed passado nas três. Fontes anteriores intactas.
Retomada exata de kernel/sampler/banco em novo processo após fechar/remover SQLite
original; três retomadas depois da correção de pista também coincidem. Elegível
para testes de integração; backend padrão do mind não foi substituído.

Nove variantes incluem gradientes 8/16/32, proteção 8/64 e histórico indiscriminado.
Mais passos/forte proteção não passaram nas três; histórico prejudicou mudança de
regra em duas. Por seed: 954 pares antigos, 10.192 passos; baseline32 10.240 passos.
Custos de IO/tempo não iguais. Candidato kernel 10.976 B + índice 19.480 B + RNG
5.056 B; p95 de consolidação 18,639/20,244/21,262 ms no ensaio pequeno em CPU.
Regularizador é sensibilidade de gradiente/âncoras periódicas, não Fisher/EWC;
sampler uniforme de pistas estruturadas, sem confiança calibrada ou latentes gerais.

17 contratos específicos passaram. Plano/laboratório registram protocolo, fonte
EWC, limites e próximo backend com suporte/confiança/ledger, fontes incompletas ou
revisadas e checkpoint compartilhado com o mind. Meta M0–M10 segue ativa;
personalidade segue adiada. Preservados resultados/arquivos anteriores e alterações
alheias do checkout; nenhum modelo instalado nem dados reais coletados.
Gate da versão corrigida: 17 contratos/0,246 s OK, discovery 306 testes/348,531 s
OK e CI final exit 0, sem alterar testes de segurança. Manifesto registra arquivos
e reavalia os pesos salvos; fonte/kernel/sampler não dependem do SQLite original.

## Alice — memória profunda, janela recente e referência Hindsight (11/10/2026)

Kernel experimental `adaptive_memory.py`/formato 36: rede linear/MLP, SGD com
momentum, MSE/Huber, decaimento e janela de até 16 pares codificados. Consulta
usa somente pesos. Escrita transacional, checkpoint limitado, retomada do
próximo gradiente exata em outro processo e restore sem aliasing/RNG alterado.
14 testes específicos passaram. Núcleo factual/temporal anterior preservado.

Três seeds, 320 encontros/640 frames novos por seed, sem reenvio de histórico à
linguagem. Ensino vem de recuperação dos pesos episódicos; chaves reservadas
ocultam o autor. Conjunção atividade/contexto, impressão reservada e nova regra
em um contexto. Dez variantes SGD e RLS. MLP/janela 16: 47/48 novas, 28/48 antigas
após segundo lote; 23/24 regra modificada e 58/72 antigas inalteradas ao final.
960/960 fatos episódicos recuperados, fontes intactas, janela apagável sem mudar
leituras. Nenhum candidato promovido: falta retenção de generalizações >=90% em
todas as fases. Capacidade top-1, não compreensão geral ou confiança calibrada.
MLP tem 548 parâmetros/10.976 B de tensores com janela 16; RLS 48 coeficientes,
precisão e 1.544 B. Orçamentos não equivalentes; custos reais no relatório.

Hindsight foi lido como referência, sem instalar/copiar execução externa: código
de consolidação usa LLM + fatos/fontes/histórico em banco; fusão combina buscas.
Inspirou registrar dependências entre hipóteses/evidências e distinguir fonte
ausente de fonte omitida por orçamento. Não substitui aprendizado nos pesos.
Plano e laboratório atualizados. Meta M0–M10 continua ativa; próximo trabalho
é estabilidade/plasticidade, reativação limitada e revisão de conclusões derivadas,
preservando as experiências anteriores. Avaliação de personalidade segue adiada.
Verificação final: discovery 289 testes/328,039 s OK; CI obrigatório exit 0 com
TEMP normal do Windows. Manifesto do lote verifica fontes/artefatos e checkpoints
de origem preservados; AST/whitespace das 98 fontes Python OK.

## Alice — integração de cenas ao mind temporal/lexical (11/10/2026)

`SceneGroundedMind` compartilha uma única sessão/banco entre eventos paralelos,
estado funcional, previsão, consolidação, palavras e coordenação de linguagem.
Frame avança relógio/preditor uma vez; foco explícito não elimina memória de fundo
nem copia campos antigos para o presente. Tracks continuam aprendidos e a fonte
é localizada/sintética. Consolidação acompanha episódios do próprio track;
falhas esperadas adiam aprendizado semântico sem perder fatos comprometidos.

Formato 35 com base 29 única, compatível com fila/intenção 30/31. Restore sem
aliasing e em processo novo; falha de validação fecha banco temporário e mantém
RNG. Correção adicional na fila fecha o banco quando o payload externo é inválido.
19 testes específicos OK; discovery 275 testes/319,779 s OK; CI geral exit 0.
Três seeds de integração: 24/24 frames, 16/16 lembranças, 8/8 respostas da política
por seed, 16 tracks e quatro páginas quentes; intenção/continuação iguais após
restore e zero fatos depois de apagar pesos. Parser de controle, sem avaliação
de linguagem natural/previsão de cenas; tempos 29/71 concorrentes com testes.

Usuário trouxe Iris para estudar processo, ALoDLM, EmbeddingGemma 2 e artigos
Titans/MIRAS/ATLAS. Fontes conferidas e PDF MIRAS lido diretamente. ATLAS via
arXiv v1; PDF OpenReview exigiu verificação, sem confirmar igualdade da revisão. Plano registra
papéis distintos e comparação futura de memória não linear/retenção/objetivos.
Sem instalar modelos novos. Personalidade segue adiada; dúvidas que alterem o
rumo podem ser perguntadas, mantendo progresso independente durante ausência.
Meta M0–M10 permanece ativa. Próximos trabalhos: relações/conjunções, avaliação
global e comparação de memória profunda sem apagar a base factual verificada.

## Alice — eventos simultâneos em páginas neurais (11/10/2026)

Sessões 33/34 aceitam PagedMemory e checkpoint episódico 24. Atualização dirigida
de episódio frio passa pela persistência. Reserva/transação por frame restaura
todo o lote em falha de escrita, inclusive páginas quentes ainda não salvas;
tracks/relógio/watermarks avançam somente após sucesso. Transações aninhadas e
endereços não reservados rejeitados. Falha nos tracks durante restore fecha a
base nova. Testes cobrem continuidade de episódios frios, revisões isoladas,
falha no segundo evento e processo novo sem SQLite original.

Três ensaios finitos de 48 frames sobre 32 eventos: pesos/resultados iguais à RAM,
88/96/84 recuperações completas e apenas duas páginas residentes; retomada exata
e controle de pesos apagados passaram. Discovery 256 testes/277,675 s OK e CI
geral exit 0; TEMP normal evitou URI incompatível do sandbox, sem mudar teste.
Integração com mind temporal/consolidação/linguagem pendente;
meta M0–M10 permanece ativa. Plano registra que o módulo de linguagem herdado
pode influenciar comportamento e requer avaliação controlada, sem antecipar como
Alice desenvolverá vínculos. Documentos contêm escopo/protocolo/limitações reais.
Usuário prefere discutir personalidade depois; linguagem coloquial/palavrões
comuns devem ser possíveis. Ponte auditada não contém filtro desse vocabulário;
comportamento herdado do modelo real ainda não verificado. RAM medida novamente
23.445.843.968 B de 33.461.567.488 B; reserva fria não cabe no teto de 75%, sem
iniciar novo host ou inferência. Avaliação real depende de admissão normal.

## Direção de arte — alternância de memória planejada (06/10/2026)

Usuário aceitou alternar LLM, ComfyUI e revisão visual, evitando acumular modelos
em RAM/VRAM. Contrato e critérios registrados em LOCAL_AI_PLAN.md: autoridade
comum de admissão, fim/liberação confirmados antes da próxima etapa, margens em
ambas as memórias, prévias limitadas, posse/cancelamento e pausa quando liberação
ou telemetria falharem. Planejamento e checkpoints persistem fora do KV cache.
Ollama externo/ComfyUI do usuário não recebem controle implícito sobre trabalhos
alheios. Trata-se de plano, sem integração implementada, geração ou download.
Verificação: test_ci.ps1 passou; diff dos documentos sem erros de formatação.
Esses checks validam a base existente, não a alternância ainda planejada.

## Streaming — correções e carregamento cancelável (06/10/2026)

Implementadas as prioridades de áudio da auditoria e o carregamento solicitado.
`CaptureProgress` mostra etapa/tempo, orientação após 10 s e cancelamento,
compartilhado no compacto/full/browser. `captureStartup` limita esperas,
cancela prompts pendentes e libera respostas tardias; watchdog global impede
inicialização indefinida. O seletor do navegador pode precisar de fechamento
manual, mas a tentativa cancelada não publica mídia recebida depois.

`CaptureSessionService` mantém dono até terminar startup/limpeza e executa
vídeo/áudio/parada em background. Ponte declarativa adicionou BeginNativeCapture,
BeginCaptureAudio, GetCaptureState e StopCaptureAudio, tipados em webview.d.ts.
Fluxo novo não usa os métodos síncronos legados. Worker recebe token próprio;
um worker ainda vivo impede nova sessão de áudio. Readiness usa TCS, sem evento
de início descartado prematuramente. Removido ganho/clipping 1,5× em estéreo
float32. Socket/worker perdido para só a faixa de áudio e mostra aviso por fonte;
vídeo continua. Recuperação é parada/reinício manual da fonte, não automática.

Diagnóstico separa RTP de áudio/vídeo e reporta ajustes de qualidade recusados.
ICE validado antes de anunciar TURN. Smoke nativo resolve versão do csproj e
captura áudio apenas do processo de teste. `StreamingTests` entrou no CI;
`capture-lifecycle.test.mjs` entrou no npm test. Testam posse, resposta tardia,
timeout/cancelamento, amplitudes, perda de áudio, silêncio, ICE e ajuste recusado.

Passaram CI, regressões de salas/captura, builds app/web e .NET, lint sem erros
(12 avisos existentes), Edge/PeerJS/WebRTC com loading/cancelamento, múltiplas
fontes e migração. WebRTC local sintético entregou 1080p60. Smoke WebView2 do
pacote novo: três inícios únicos em 411/314/325 ms, própria janela 800×600;
áudio real de processo do app isolado iniciou e sobreviveu ao silêncio,
sem captura de áudio pessoal do sistema. Testes entre PCs/redes e avaliação
auditiva do conteúdo real continuam necessários.

Empacotador oficial gerou 0.2.4, sem incrementar versão, e atualizou a raiz.
Backup anterior em `Backup/before-stream-startup-20261006-035937/`.
ZIP: `Backup/Xennex-v0.2.4-win64.zip`, SHA256
`AB9280BE60AC3DF01850726ACFE645C466836487D3A42C2D03E3C9CC4B17179D`.
Sem commit/deploy. Limites arquiteturais permanecem: um WGC nativo por instância,
mesh/upload por cópia, sem TURN padrão. Novas funções sociais/colaboração ainda
aguardam as próximas etapas do plano. Detalhes em [STREAMING.md](STREAMING.md).

## Auditoria do streaming antes de ampliar funcionalidades (06/10/2026)

Usuário pediu verificar primeiro o serviço atual, antes de implementar funções
inspiradas no GoLive. Relatório em [STREAMING_REVIEW.md](STREAMING_REVIEW.md),
ligado a STREAMING.md. Sem alteração da lógica de streaming, pacote/executável,
commit ou deploy. Builds React/app e web regenerados pelos comandos oficiais.

Passaram npm test, builds React/web e .NET (zero avisos/erros), CI completo,
integração Edge/PeerJS/WebRTC com três transmissores, múltiplas telas/câmera,
áudio/layouts, entrada tardia e migração após saída/queda abrupta. Ensaio WebRTC
local sintético entregou 1920×1080 a 60 FPS. Smoke nativo da cópia limpa 0.2.4
capturou apenas a própria janela 800×600 em três ciclos, primeira tentativa,
com primeiro frame em 2769/264/251 ms; token/navegação indevidos rejeitados.
Manifesto público Cloudflare respondeu HTTP 200 com xennex-room-v3/série 0.2.

Reprodução sintética em bin/streaming-review/audio-disconnect.mjs confirmou
perda silenciosa do socket de áudio após abertura: faixa continua ativa,
sem aviso/recuperação. Código também mantém espera síncrona de áudio (até 4 s
mais limpeza), ganho fixo 1,5 com clipping no ramo estéreo float32 e diagnóstico
limitado a vídeo. Captura nativa é uma por instância; seis publicações não
significam seis workers WGC. Mesh divide upload por conexão; preservar resolução
não garante 1080p60 na internet. Sem .env ativo/TURN nos builds desta rodada.

Próximas prioridades propostas: áudio/confiabilidade, métricas/qualidade,
capturas nativas independentes e carga, depois voz/chat, mídia sincronizada e
colaboração. Sem dependência paga obrigatória. Testes entre PCs/redes e escuta
de áudio real continuam pendentes; os testes locais não validam esses casos.

## Biblioteca VR — navegação livre e tamanho (05/10/2026)

O usuário esclareceu que anterior/próxima já funciona quando há várias
imagens selecionadas; faltava navegar por pastas/acervo e aumentar o painel.
**Abrir no VR** agora oferece Biblioteca completa por padrão, sem seleção
obrigatória, mantendo a visão/filtros atuais. Dentro do headset há Galeria,
Explorador, Acervos, subpastas, pasta acima, favoritos, ordenação, atualização
da consulta e páginas de 12 entradas. O visualizador atravessa páginas e
retorna à origem. Seleção atual continua explícita, limitada a 100 imagens;
não interpreta pasta selecionada como lista recursiva. Edição fica no desktop.

O painel começa com 2 m de largura. **Tamanho** ajusta largura e distância
do painel fixado, entre 0,75 e 3 m, independentemente do zoom da imagem.
Retornar dos ajustes preserva imagem/pasta; valores são por sessão.
`VrPanelLayout` compartilha alvos entre desenho e entrada; `VrPointerInput`
guarda MouseMove por cursor/overlay e confirma o gatilho sobre o mesmo alvo,
sem depender das coordenadas do release. Miniaturas novas passam a limitar
também altura antes da decodificação, evitando alocações grandes com imagens
muito altas. Catálogo pessoal, skins e configurações não são modificados.

Validação: CI completo, build React/C# (0 avisos/erros C#), UI Playwright da
Biblioteca, lint sem erros (12 avisos preexistentes), catálogo sintético de
126 imagens, navegação entre páginas/subpastas, limites e eventos de controle
passaram. Smoke SteamVR real passou para galeria, explorador, acervos,
texturas, fixação, tamanho/distância, descarte e reabertura. Prévias sintéticas
em `bin/vr-ui/`. Cliques físicos e conforto da nova UI precisam do teste do
usuário; não afirmar privacidade contra Oculus Mirror. Detalhes em [VR.md](VR.md).

Build anterior preservado em `Backup/before-vr-browser-20261005-140657/`.
O empacotador oficial gerou e validou o ZIP 0.2.4 e atualizou o executável
da raiz. Assinatura Authenticode válida e SHA256 idêntico ao executável do
pacote foram conferidos. Versão continua 0.2.4; sem commit ou publicação.

## Revisão visual e Liquid Glass (04/10/2026)

Os acabamentos das skins foram separados da geometria: `skin-theme.css`
mantém os tokens, `skin-layout.css` mantém posições e `skin-surfaces.css`
concentra vidro/sólido/terminal/ornamentado e o novo **Liquid Glass**. O
preset opcional **Liquid Moon** usa azul noturno, bordas suaves douradas,
reflexos estáticos e cantos arredondados, inspirado na referência do usuário.
Nenhuma skin pessoal é substituída ou ativada automaticamente.

**Estrutura → Acabamento** permite aplicar somente o acabamento à skin atual;
**Painéis → Reflexos do Liquid Glass** regula sua intensidade de 0 a 1.
O contrato C#/TypeScript e a persistência foram atualizados com normalização
compatível com skins antigas. Biblioteca, IA, transmissões e painel compacto
recebem o acabamento através de tokens e seletores escopados. O editor mantém
sua própria paleta e as superfícies de mídia/cores semânticas são preservadas.
Desfoque se limita aos painéis maiores; não há filtros de deslocamento ou
animação JavaScript por quadro. O efeito é CSS, sem refração física ou mudança
na animação/posição nativa do modo compacto. FPS não foi medido no hardware.

`test_ci.ps1`, build React/C#, lint (somente avisos anteriores), testes de UI
da Biblioteca e do compacto e teste nativo de skins passaram. O teste nativo
confirmou salvar/reabrir o acabamento e a intensidade sem tocar em `Data/`
ou skins pessoais. Prévias estão em `bin/compact-ui/liquid-moon-*.png`.
Detalhes e revisão da organização em [SKINS.md](SKINS.md).

O empacotador oficial gerou/validou o pacote 0.2.4 e atualizou o executável
da raiz, cuja assinatura e SHA256 foram conferidos contra o pacote. A cópia
anterior ficou em `Backup/before-liquid-glass-20261004-064520/`. Não houve
publicação, commit ou alteração dos dados pessoais.

## Biblioteca no SteamVR / Rift S — protótipo (03/10/2026)

Após o usuário confirmar SteamVR/Meta Link/headset conectados, foi criado um
visualizador próprio da Biblioteca em OpenVR. `AssetVrService` isola sessão,
cancelamento e worker; `VrGallerySession` valida até 100 IDs de imagens;
`VrPanelRenderer` compõe uma superfície RGBA 1280×800 somente quando muda;
`OpenVrOverlay` gerencia dashboard, painel fixo e input. A DLL vem somente do
runtime registrado e o binding oficial Valve está fixado na revisão indicada
em [VR.md](VR.md), com licença incluída no build. A ponte permanece declarativa.

**Abrir no VR** usa a seleção atual ou as imagens da página e permite minimizar
à bandeja somente após conexão bem-sucedida. O painel tem anterior/próxima,
zoom, ajustar, fixar, centralizar e fechar. Fechar não restaura automaticamente
a janela principal. Não há captura de desktop ou janela de espelho do Xennex;
Oculus Mirror/SteamVR ainda podem espelhar. O usuário aceita outra área de
trabalho para o espelho. Não prometer invisibilidade ou VR de todo o aplicativo.

Build C# sem avisos/erros, build React, UI da Biblioteca (incluindo minimização
condicional e falha de conexão) e `test_ci.ps1` passaram. O smoke real no
SteamVR passou para upload, navegação, pin/recenter, descarte e reabertura;
o usuário confirmou a imagem sintética amarela/laranja no headset. A miniatura
é liberada pelo dashboard e não deve receber `DestroyOverlay` independente.
Pendente manual: cliques físicos, conforto e espelhamento com a seleção real.
Evoluções de miniaturas, edição de tags e outros runtimes ficam no plano VR.

O empacotador oficial gerou e validou o pacote 0.2.4 e atualizou `Xennex.exe`
da raiz; o SHA256 do executável local coincide com o do pacote assinado.
O build anterior foi preservado em `Backup/before-vr-20261003-040428/`.
Os dados pessoais permaneceram fora do pacote. Não houve publicação ou commit.

## Consolidação para o próximo commit (29/09/2026)

O último commit é `a57d925` (0.2.3, 12/09). As mudanças acumuladas até 0.2.4
foram agrupadas por área em [CHANGELOG.md](../CHANGELOG.md), com links aos
manuais específicos e limites ainda sujeitos a verificação manual. Scripts
auxiliares deixaram de gravar caminhos absolutos do perfil de desenvolvimento:
o inspetor usa `%TEMP%/Xennex/Screenshots` por padrão, e o sincronizador do
Obsidian usa `--vault` ou `XENNEX_OBSIDIAN_VAULT` e resolve `docs/` pelo próprio
repositório. O build local do frontend/app/CaptureWorker, o build web, `npm test`,
quatro testes de interface, lint e `test_ci.ps1` passaram. Os avisos do lint
permanecem sem erro. Não houve publicação nem mudança em `Data/`.

## Aparência estrutural das skins (29/09/2026)

As skins agora incluem posições da navegação e dos controles da janela,
apresentação flutuante/preenchida, acabamento vidro/sólido/terminal/ornamentado
e ordem dos atalhos principais. O editor tem seção **Estrutura**, quatro
presets e prévia com desfazer/descartar. Configurações continua fixa no fim.
SkinRepository e o frontend validam as escolhas e normalizam skins antigas.
CSS de geometria só atua na janela cheia; o compacto mantém o layout WPF.
`npm run build`, `compact-ui.test.mjs`, `SkinTests`, `test_ci.ps1`, lint e
`run_dev.ps1 -BuildOnly` passaram. O lint conserva avisos anteriores de outros
módulos. O build de desenvolvimento foi preparado em `bin/Release/net8.0-windows`.

## Destino visual e busca no acervo (29/09/2026)

Os diálogos de mover/copiar/criar pasta ganharam seletor visual de destino com
pastas cadastradas, subpastas paginadas, filtro local e caminho clicável. A
consulta ao catálogo ganhou `DirectoriesOnly` para listar somente diretórios.
**Busca rápida** (Ctrl+K) abre pesquisa em todos os acervos cadastrados, com
debounce de 180 ms e caminho nos resultados. Ela usa o índice atual do Xennex;
não equivale à indexação de discos/MFT do Everything nem ao mapa de espaço do
WizTree. Operações físicas continuam exigindo prévia e confirmação nativas.
Build local, UI da Biblioteca, lint e `test_ci.ps1` passaram; o lint ainda
mostra avisos anteriores fora deste módulo.

## Seleção e organização em lote na Biblioteca (29/09/2026)

Galeria e Explorador agora exibem **Selecionar vários**, **Selecionar página**,
**Limpar seleção** e acesso à edição de lote na barra de arquivos. Shift+clique
seleciona intervalo na página; clique direito preserva o lote já selecionado e
abre menu com edição de catálogo e operações de arquivo. O backend já limitava
o lote a 100 itens e exigia prévia/confirmação para copiar, mover ou enviar à
Lixeira; essa proteção foi mantida. O teste de UI cobre os dois modos. `npm run
build`, `node tests/assets-ui.test.mjs`, `npm run lint` e `test_ci.ps1` passaram;
o lint ainda mostra avisos preexistentes fora da Biblioteca.

## Eco no compartilhamento web (29/09/2026)

O seletor web passou a solicitar `restrictOwnAudio` quando suportado e a preferir
`windowAudio: "window"`. O aviso da interface explica que uma captura de tela
inteira pode conter áudio de chamadas em outros apps/abas. O navegador controla a
fonte escolhida; Cloudflare hospeda a página e não consegue acessar ou excluir
processos locais. A mudança requer build e publicação web separados.

## Ícone e restauração da instância única (29/09/2026)

O ícone do executável (`assets/icon.ico`) agora também é usado na bandeja e nas
janelas principal/visualizador. Nas janelas, é carregado do executável em C#;
um caminho `.ico` direto no XAML causou erro de `TypeConverterMarkupExtension` na
inicialização e foi removido. A segunda abertura sinaliza a instância existente
por mutex e evento nomeados na sessão do Windows; o processo principal restaura
a janela pela Dispatcher mesmo quando ela está oculta na bandeja. Isso substitui
a busca por nome de processo e o broadcast de mensagem Win32, que dependia da
janela oculta receber uma mensagem. É preciso encerrar a versão antiga uma vez
antes de testar o novo build, pois ela ainda usa o protocolo anterior.
O build Release passou com zero avisos. No teste com dois processos do build de
desenvolvimento, a primeira janela permaneceu aberta e a segunda saiu com código
0; a restauração a partir da bandeja ainda pede teste manual pela interface.
Versão incrementada para 0.2.4 antes do pacote local, preservando o pacote 0.2.3
e permitindo que o atalho existente use o executável atualizado na raiz.
O empacotador oficial gerou e validou `Backup/Xennex-v0.2.4-win64.zip`, assinou
os executáveis e atualizou `Xennex.exe` na raiz sem tocar em `Data/`. A assinatura
da raiz foi validada; a primeira execução abriu com janela e a segunda saiu com
código 0 sem duplicar o processo. O teste de restauração depois de minimizar à
bandeja segue manual, pois o teste automatizado apenas cobriu a janela aberta.

## Metadados de geração na Biblioteca (29/09/2026)

O inspetor da Biblioteca passou a resumir o grafo `prompt` embutido em PNGs do
ComfyUI: checkpoint, LoRAs e intensidades, prompts ligados ao sampler, seed,
steps, CFG, sampler, scheduler, denoise e dimensões. Cada sampler recebe seu
próprio resumo; o texto original permanece acessível abaixo. A interpretação
acontece na interface sobre os metadados já catalogados, sem reindexar nem
alterar a imagem. Metadados podem ser editados e não provam autoria por IA.

## Biblioteca de artes (28/09/2026)

Correção posterior: a raiz `Xennex.exe` de 27/09 foi aberta com o `wwwroot`
compilado em 28/09 e retornou `0x80020006` ao selecionar pasta, pois faltavam os
métodos da Biblioteca no processo. A UI agora informa incompatibilidade de versões,
desativa o seletor antigo e oferece **Expandir área** para recolher o cabeçalho e
subir Galeria/Explorador. Os diálogos de pasta/backup receberam a janela WPF como
proprietária para permanecerem visíveis sobre o app. O teste de UI cobre ambos os
estados e a incompatibilidade simulada.
Após `test_ci.ps1`, UI e WebView2 nativo passarem, o empacotador oficial gerou um
pacote local assinado v0.2.3 e atualizou `Xennex.exe` na raiz. O pacote anterior foi
preservado em `Backup/Xennex-v0.2.3-win64-before-biblioteca-20260928*`. Não houve
publicação nem alteração dos dados pessoais em `Data/`.

Criada a aba Biblioteca sobre pastas locais escolhidas pelo usuário, com Galeria e
Explorador no mesmo catálogo SQLite (`Data/assets/`). Índice em segundo plano,
miniaturas por ID, PNG de geração, busca/regras, tags, favoritos, notas, coleções,
comparação de imagens, abas e segundo painel. Operações físicas têm prévia,
confirmação, diário e recuperação; desfazer cobre renomeação/movimento de arquivos
da mesma unidade. Há relocalização de raiz offline, backup do catálogo e superfície
compacta. A integração C#/React usa ponte tipada e handler de mídia específico.

O manual [ASSET_LIBRARY.md](ASSET_LIBRARY.md) distingue as funções atuais do plano
[ASSET_LIBRARY_PLAN.md](ASSET_LIBRARY_PLAN.md): virtualização contínua, alguns
atalhos e movimentos entre volumes, canvas, busca por cor e integrações de geração
permanecem pendentes. Testes isolados em `scripts/tests/AssetLibraryTests/`, UI em
`frontend/tests/assets-ui.test.mjs` e WebView2 real em
`scripts/tests/test_assets_native.ps1`. Dados e originais do usuário não entram nas
fixtures.

Validação em 28/09/2026: `test_ci.ps1`, build C#, build frontend, teste UI e
teste nativo WebView2 passaram; 43 checks em AssetLibraryTests. Benchmark sintético
10 mil entradas: índice 9,55 s, buscas p95 4,5 ms, 66 MiB privados. Ainda requer
teste manual no acervo real antes de declarar esta área pronta para release.

## Animação e revisão documental (27/09/2026)

O timer de 16 ms foi substituído, durante movimentos, por CompositionTarget.Rendering.
CompactFrameCadence limita callbacks a 30/60/120 FPS ou acompanha renderização
no modo Automático (padrão). SidebarAnimationFps persiste pela ConfigService;
o seletor fica em CompactPlacement. Duração continua baseada em tempo.
Não voltar a usar DispatcherTimer como relógio da animação nem enfileirar
quadros atrasados. Timer de 50 ms cuida apenas de hover/estado parado.

Revisadas as regras adicionadas com ferramentas locais: visão de especialistas
preservada, garantias absolutas removidas, notas JSON versus exportação Markdown
esclarecidas, recursos futuros identificados e verificações de empacotamento
restauradas. .cache/ ignorada para não versionar o índice local.
Auxiliares recentes em scripts/ passaram apenas por verificação de sintaxe;
não alegar que já estão integrados ou funcionalmente validados na aba de IA.

## Painel compacto (26/09/2026)

Implementado e revisado: interfaces por área, editor de skins no compacto,
posição aberta separada de recolhimento Top/Left/Right/Auto. Auto escolhe a
borda real mais próxima. CompactMotion usa interpolação por tempo; a alça
permanece acessível e o canvas mantém tamanho fixo. Interação inclui o editor.
Chat e rascunhos da IA são compartilhados. Testes incluem WebView2/COM reais.
COMPACT_MODE_NEXT.md registra apenas incrementos futuros.

Ver COMPACT_MODE.md: launcher próprio preserva rotas montadas. SidebarService
remove o mínimo da janela normal durante o compacto e restaura seu estado.
Recolher encolhe o viewport dentro do monitor; nunca deslocar a parte oculta
para um monitor vizinho. Geometria em pixels físicos; layout interno fixo.

## Fluxo principal

O Xennex combina .NET 8/WPF e WebView2 com React/TypeScript. A janela hospeda
`https://appassets/index.html`, mapeado para a pasta externa `wwwroot/`.
O frontend chama `window.chrome.webview.hostObjects.api`; `ApiBridge` delega
para os serviços C#. A janela também recebe mensagens de arraste e resize.

A transparência usa Win32 e ColorKey. Preserve o mecanismo da janela ao mexer
na interface; alterações visuais devem ocorrer no React/CSS.

## Mapa do código

| Diretório/arquivo | Responsabilidade |
| --- | --- |
| `src/Program.cs` | Entrada, instância única e registro de exceções globais |
| `src/UI/` | Janelas WPF, WebView2, bandeja e ciclo de vida visual |
| `src/Interop/ApiBridge.cs` | Contrato COM de comunicação com os serviços |
| `src/Models/` | Configuração, skins, builds e resultado de atualização |
| `src/Services/` | Recursos do Windows, dados e serviços do aplicativo |
| `src/Services/NativeCaptureService.cs` | Inicialização e encerramento do processo de captura |
| `src/Services/StreamService.cs` | Janelas dos visualizadores e fachada para captura |
| `src/Services/Updates/install_update.ps1` | Script incorporado ao assembly e extraído para aplicar atualizações |
| `src/CaptureWorker/` | Projeto separado para Windows Graphics Capture |
| `frontend/src/App.tsx` | Escolha entre aplicativo principal e visualizador |
| `frontend/src/AppRoutes.tsx` | Renderização das abas |
| `frontend/src/layout/` | Moldura, navegação e barra de título |
| `frontend/src/hooks/` | Estado do aplicativo, auto-hide e notificações |
| `frontend/src/features/` | Dashboard, jogos, IA local, cloud, gestos, configurações, skins e transmissão |
| `frontend/src/features/stream/peerConfig.ts` | Configuração PeerJS compartilhada por host e viewer |
| `frontend/src/components/` | Componentes compartilhados |
| `frontend/src/styles/` | Estilos separados por área |
| `frontend/src/index.css` | Entrada CSS; ordem explícita dos módulos |
| `frontend/src/webview.d.ts` | Tipos da ponte C# e callbacks nativos |
| `frontend/watch.html` | Visualizador web independente |
| `cloudflare_pages/` | Instruções e dist gerado para hospedagem externa |
| `wwwroot/` | Saída do Vite e skins; não editar os bundles manualmente |
| `assets/defaults/` | Modelos públicos opcionais para releases |
| `Data/` | Configurações pessoais; nunca fonte de empacotamento |
| `scripts/lib/ReleaseValidation.ps1` | Validação de frontend, pacote e caminhos de limpeza |
| `scripts/tests/test_release.ps1` | Testes isolados de pacote e cópia de atualização |

## Contratos a preservar

- Cada aba mantém seu componente. Jogos, IA e transmissão permanecem montados
  entre navegações; seus providers/controllers também alimentam o compacto.
  Não desmontar sessões, rascunhos ou conexões ao trocar a apresentação.
- Os módulos CSS são importados na ordem original. Não reordene imports sem
  verificar a cascata, incluindo estilos do visualizador.
- O TypeScript está em modo `strict`. Novos métodos nativos devem constar em
  `webview.d.ts`; o protocolo de salas é validado em `features/stream/protocol.ts`.
- Erros gerais e falhas da ponte usam `AppLog`; serviços também mantêm seus
  logs específicos. O logger não deve impedir o encerramento do aplicativo.
- `StreamService` mantém a fachada pública da captura. `NativeCaptureService`
  controla o processo auxiliar; o pipeline de mídia permanece nos módulos existentes.

## Build, distribuição e atualização

Use `scripts/run_dev.ps1` para compilar e abrir um build local. Veja
[TESTING.md](TESTING.md) para o roteiro e o isolamento de configurações.

A versão oficial é `<Version>` em `Xennex.csproj`. O empacotador lê esse valor e
rejeita `-Version` divergente. Os metadados do aplicativo derivam dessa propriedade,
e o publish do worker recebe a mesma versão.

Para distribuição, use exclusivamente `scripts/package_release.ps1`.
Os dois executáveis são publicados self-contained para win-x64. `wwwroot/`,
`WebView2Loader.dll`, dados padrões e scripts ficam ao lado deles no pacote;
não estão todos embutidos em um único executável.

Somente a skin `default` é distribuída. Templates de dados vêm de
`assets/defaults/`, nunca de `Data/`. O atualizador preserva arquivos existentes
em `Data/` e ignora skins recebidas que não sejam `default`.

O WebView2 Runtime é externo; REAL requer seu executável. Gestures inclui seu
motor autocontido em scripts/Xennex.GesturesWorker.exe, compilado e assinado pelo
empacotador. Veja [GESTURES.md](GESTURES.md) para reconhecimento, memória e testes.

Regras: [CODING_RULES.md](CODING_RULES.md), [AGENTS.md](../AGENTS.md) e
[release-packaging.md](../.agents/rules/release-packaging.md).

Streaming v0.2: consulte [STREAMING.md](STREAMING.md) para arquitetura, limites e validação.

Salas v3: `RoomCoordinator.ts` é migrável; `RoomClient.ts` preserva os peers de mídia.
Cada participante publica um catálogo de fontes, com assinatura/áudio independentes.

## Análise de jogos

A aba Jogos substitui a tela demonstrativa WuWa. Contratos e persistência estão
em `src/Models/GameAnalytics/` e `src/Services/GameAnalytics/`; interface em
`frontend/src/features/games/`. A ponte oferece GetGameLibrary, SaveGame e
ImportGame. Documentos pessoais e backups ficam somente em Data/games.
Consulte [GAME_ANALYTICS.md](GAME_ANALYTICS.md) para o recorte implementado e
[FUTURE_LIFE_HUB.md](FUTURE_LIFE_HUB.md) para a futura migração do hub de rotina
que o usuário mantém no Google AI Studio.

A área Jogos abre por padrão no espaço visual: capa e galeria de personagens,
quadros arrastáveis com conexões, zoom e editor lateral. O esquema 2 incorpora
imagens e planos; GameStore migra a leitura do esquema 1 sem regravar o original.
A aba permanece montada entre navegações para preservar rascunhos; persistência
visual exige Salvar espaço visual. Veja GAME_ANALYTICS.md para limites e migração.

Jogos agora usa esquema 3 com definições livres de skills, ações, métricas e
contextos. Modelos na criação são editáveis em Definir jogo. Sem galeria, a área
visual mostra habilidades. SessionEventsEditor registra sequências; GameHistory
agrega resultados por contexto. Renomear uma definição preserva snapshots dos
registros. GameMigration mantém IDs estáveis ao ler arquivos 1/2.

## IA local

A aba IA local mantém chat e rascunhos montados entre navegações. Serviços em
src/Services/LocalAi: LocalAiService coordena a fila, AiStore persiste Data/ai,
LocalModelClient fala somente com HTTP loopback e WindowsResourceProbe mede RAM
via GlobalMemoryStatusEx e VRAM global via DXGI/PDH. ResourcePolicy é pura e testável.
Modelos/motores são opcionais externos; nenhuma chamada paga ou download automático.
A GPU monitorada é o adaptador dedicado com maior memória; configure o motor para
esse adaptador. Uma chamada por vez, margem padrão de 25%, reservas extras explícitas,
pausa por pressão e recuperação de checkpoints sem repetir trabalhos após reinício.
O ciclo de vida da janela delega o encerramento à ponte/serviço. Plano completo e
limitações em LOCAL_AI_PLAN.md. Salas e especialistas estão disponíveis; ferramentas
e treinamento permanecem futuros.

Incremento Ollama (19/09): AiRuntimeService e OllamaProcessHost gerenciam somente
uma instância própria na porta 11436 (cloud desabilitado); detectam também a porta
11434 e o endpoint salvo. OllamaChatClient implementa NDJSON, contexto, CPU e
keep_alive. ModelMemoryEstimator/JobMemoryObservation usam metadados e deltas
observados; não alegar reserva física nem pico exato. AiLibrary usa esquema 2,
migrando o esquema 1 com backup .v1.bak; dados ficam no mesmo Data/ai privado.
Novo formulário detecta/seleciona modelo sem alterar configuração até Salvar.
Testes: 104 checks; WebView2/COM nos dois protocolos e salas; --rooms-real usa
llama3 instalado, orçamento 75%, dois especialistas, residência e liberação.

Incremento de salas (20/09): LocalAiRooms é parte de LocalAiService. Cada trabalho
aponta para MessageId; não usar Messages.Last() para streaming/completar trabalhos.
AiRoomContext seleciona contexto e registra fontes; AiRoomValidation valida limites.
Plano versionado, cadernos revisáveis e execuções com avaliações persistem no JSON.
Falha/cancelamento interrompe dependências da reunião; nunca repetir após reinício.
Guia em [LOCAL_AI_ROOMS.md](LOCAL_AI_ROOMS.md) e arquitetura de cadernos/memória em [AI_SPECIALISTS_AND_MEMORY.md](AI_SPECIALISTS_AND_MEMORY.md). Ajuda ainda é conversacional, sem ferramentas executáveis.

## Skins (20/09/2026)

Editor global via portal em AppShell, com prévia separada da skin salva, histórico
e salvamento de cópias. useAppState e editor mantêm referência estável à ponte COM;
reler hostObjects.api como dependência de efeito podia recarregar o rascunho.
SkinRepository valida caminhos/JSON, mantém extensões e clona assets referenciados.
Default é protegida contra edição/importação: gerar cópia pessoal. Detalhes e
testes em SKINS.md. Skins concluídas; IA retomada com o incremento de salas.
Decisões e próximos incrementos registrados em LOCAL_AI_PLAN.md.
Continuidade (20/09): AiHistoryWindow seleciona trocas completas; AiRoomContext
as envia em ordem cronológica, mantendo assistant para o próprio especialista.
Excertos são explícitos em ExcerptMessageIds. Não voltar a transformar todo o
histórico em user nem preservar perguntas antigas quando suas respostas saem.
Ollama próprio usa Data/ai/models quando preparado; diretório/pesos são privados.
Novos modelos, limitações e avaliação estão em LOCAL_AI_MODELS.md.

## Segurança e CI (revisão de 21/09/2026)

Ver SECURITY_REVIEW.md para achados confirmados, correções e pendências. CI em
.github/workflows/ci.yml compila React/web/.NET e chama npm test e test_ci.ps1;
a execução no GitHub depende do commit/push. Não publicar nem assinar pelo CI.
LocalWebServer resolve somente caminhos sob wwwroot e não oferece CORS wildcard.
WebSockets de áudio/vídeo exigem Origin https://appassets e token por execução,
obtido por GetCaptureToken; app e CaptureWorker precisam ser atualizados juntos.
WebViewSecurity restringe a navegação da interface com ponte nativa.
UpdatePolicy exige release estável mais recente, ZIP oficial exato e digest GitHub;
instalador repete hash, valida ZIP/assinante e confirma preparo antes do app fechar.
Fingerprint público em assets/publisher-thumbprint.txt; empacotador não gera chave.
Pendências: ciclo de vida assíncrono do áudio, logs unificados, mensagens tipadas,
rollback da instalação e manifesto assinado de todos os assets. Nenhum commit
ou deploy foi feito nesta revisão; preservar todo o trabalho anterior da árvore.

## Biblioteca — visualizador, painéis e edição em lote (28/09/2026)

As setas do visualizador passam para uma barra central inferior para não competir
com a sidebar automática do Xennex. O painel duplo oferece disposição horizontal
ou vertical com proporção de 25–75%, persistida na WebView; fechar o principal
promove a pasta secundária e fechar o segundo conserva o principal. Seleções de
até 100 itens podem receber favorito, tag e associação a coleção num único lote
transacional SQLite, com validação de todos os IDs e rollback integral em erro.
Detalhes de uso e limites em ASSET_LIBRARY.md. A referência Gryphlink pode ser
aproximada com os controles existentes de opacidade, blur, raio e borda no editor
de skins; não foi aplicada mudança global que altere skins pessoais.
Validação: build e lint React, 47 checks AssetLibraryTests, teste Playwright da
Biblioteca, CI completo e smoke WebView2/COM com escrita e leitura após reinício
passaram. O teste nativo deixou de exigir o cabeçalho visível porque o modo
Expandir área persiste e o oculta. Pacote assinado 0.2.3 foi gerado pelo script
oficial e copiado para a raiz; o ZIP anterior foi preservado com sufixo
`before-biblioteca-layout-20260928`.

## Biblioteca — metadados visuais e catálogo de termos (29/09/2026)

A ficha de imagem abre um mapa somente de leitura dos nodes e conexões do
ComfyUI, aceitando `prompt` de execução e `workflow` visual como fallback.
Resumo e texto original ficam em abas da mesma janela. Tags manuais e termos
extraídos de prompts positivos/negativos aparecem juntos ou separados em um
catálogo paginado, pesquisável e clicável para filtrar a galeria. Os termos de
prompt são índice derivado em SQLite, preenchido em lotes quando consultado;
modificação do arquivo invalida a entrada por timestamp/comprimento de metadados.
Nenhum prompt é copiado para serviços externos nem usado como avaliação da imagem.
Extração heurística e limites estão em ASSET_LIBRARY.md. A classificação pessoal
de gerações boas/ruins permanece futura e deve ser armazenada separadamente da
polaridade do prompt.
Validação: build .NET/React, 52 checks do catálogo, testes Playwright da
Biblioteca, CI completo e smoke WebView2/COM com escrita e leitura após
reinício passaram. O lint não apontou erros; os avisos são de outras áreas.
Pacote 0.2.4 gerado pelo script oficial, com assinatura válida e executável
da raiz idêntico ao pacote. O ZIP anterior foi preservado com sufixo
`before-tags-nodes-20260929`.

## Biblioteca — descoberta rápida de metadados (29/09/2026)

Filtro **Com metadados** e selo META usam apenas o catálogo SQLite para localizar
imagens com texto PNG; a listagem transfere um booleano em vez do JSON completo.
Uma revarredura consulta tamanho/data de modificação sem carregar o texto salvo
para cada arquivo inalterado. O texto é relido do PNG somente quando o arquivo
muda. A busca continua limitada aos formatos que o leitor de metadados suporta.
Validação: 55 checks do catálogo, teste Playwright da Biblioteca, smoke
WebView2/COM com reinício, CI completo e build React passaram. O lint terminou
sem erros, com avisos de outras áreas. Pacote assinado 0.2.4 e executável da raiz
atualizados; o ZIP anterior está salvo com sufixo `before-metadata-filter-20260929`.

## Skins — cartões e blocos de Configurações (29/09/2026)

O editor de skins agora oferece cor/opacidade de fundo e borda, cantos,
espaçamento interno e distância entre cartões. A seção Estrutura permite
reordenar os quatro blocos de Configurações e escolher uma ou duas colunas,
com retorno automático para uma coluna em janelas estreitas. As propriedades
novas têm defaults compatíveis com skins anteriores e são normalizadas tanto
no frontend quanto em SkinRepository. A prévia usa as mesmas variáveis CSS
que a skin salva. Detalhes em SKINS.md.
Validação: build e lint do frontend, teste Playwright do editor/layout,
27 checks nativos de skins, CI completo e build local .NET/worker passaram.

## Biblioteca — nomenclatura e conflitos em lote (01/10/2026)

Renomear aceita seleção múltipla; copiar e mover oferecem o mesmo editor de
nomes. Regras declarativas usam `{base}` e `{number}`, preservam extensões,
permitem padding, início manual ou continuação após o maior número compatível
na pasta de destino. É possível aplicar ao lote inteiro ou apenas aos nomes
em conflito, ordenar por nome/data/seleção ou reorganizar miniaturas com alças
e setas, além de definir nomes individuais ou ignorar itens. A prévia reserva
nomes entre todos os arquivos do lote; conflitos não resolvidos bloqueiam a
confirmação, e qualquer mudança nas opções invalida a prévia anterior.

O backend revalida todos os itens ativos antes do primeiro movimento e mantém
checagens por arquivo, identidade no catálogo e histórico de desfazer. Nenhum
destino existente é sobrescrito. `AssetNamingSequence` isola a interpretação
do padrão; `AssetNamingEditor` isola os controles visuais. A ponte de prévia
roda em Task para não bloquear a UI ao procurar a última numeração. Limites:
100 itens, numeração de arquivos até 999999999, sem troca cíclica de nomes nem
transação física do lote inteiro. Detalhes de uso em ASSET_LIBRARY.md.

Validação: build/lint React (somente os avisos preexistentes de outras áreas),
85 checks AssetLibraryTests, teste Playwright com ordem, regras, nomes por
arquivo, ignorados e invalidação de prévia, CI completo e smoke WebView2/COM
com prévia assíncrona, conflitos e persistência após reinício passaram.
Pacote 0.2.4 gerado pelo empacotador oficial, com executável da raiz idêntico
ao pacote e assinatura conferida. O ZIP anterior foi preservado com sufixo
`before-batch-naming-20261001`. Nenhum commit ou publicação foi feito.

## Alice — primeiro laboratório de memória neural (10/10/2026)

O usuário esclareceu que quer experiências aprendidas em pesos e associadas a
imagem/áudio, com partes neurais integradas ao mesmo processamento; autorizou
começar o experimento. Foi criado `scripts/alice_memory/`, isolado do app:
pequenos encoders de pixels/espectros alinhados num espaço de 16 dimensões,
congelados antes de gerar associações aleatórias de dono/lugar/apelido. A memória
tem 2.128 parâmetros e aprende com imagens; recupera também por áudio sem ler
notas, respostas esperadas ou IDs na consulta. O checkpoint contém apenas pesos
e versão; há CLI de treino/avaliação e consulta PNG/WAV em processo novo.

Validação: oito testes dedicados passaram, incluindo três sementes (17/29/71),
controles com memória zerada e sinais de outra identidade, pesos perceptivos
inalterados, correção e consulta com arquivos renomeados em pasta sem dataset.
Na semente 17, recuperação exata em 96 imagens e 96 sons reservados: 0% antes,
100% após treino sequencial com replay e após correção. Sem replay, a recuperação
das quatro identidades antigas caiu para 0%. Replay usa exemplos latentes durante
treino; a consulta final usa só os pesos. Resultado não comprova aprendizado
irrestrito ou memória exclusivamente paramétrica em todo o ciclo.

CI completo aprovado fora do sandbox, que bloqueava HttpListener/loopback. TEMP
foi apontado somente nessa execução para uma pasta isolada sem espaços/escapes,
evitando uma limitação do teste existente de caminho legado. Nenhum código ou
expectativa de teste existente foi alterado. PyTorch 2.4.1+cpu já estava instalado;
sem novas dependências, downloads, dados pessoais, câmera, microfone ou GPU.

Contrato/uso/limites em `docs/ALICE_NEURAL_MEMORY.md`; ensaio preservado em
`bin/AliceMemory/pilot-seed17/`. Isso é um classificador associativo sintético de
oito identidades conhecidas, não uma LLM nem integração com o núcleo de um omni.
Próximo passo: escolher backend/backbone compatível e treinar a interface interna
com a memória, além de avaliar novidade, capacidade e retenção. Chat, cadernos,
modelos e fila atuais preservados. Sem commit, pacote ou publicação.

## Alice — acontecimentos e revisao incremental sem replay (10/10/2026)

O usuario pediu continuidade de experiencias e revisao do passado, exemplificando
a refeicao inicialmente atribuida ao pai e depois a mae. Foi acrescentado um
segundo recorte ao laboratorio: `online_memory.py`, `streaming.py` e comandos
`stream`/`stream-query`. A memoria usa pesos associativos atualizados por minimos
quadrados recursivos e uma matriz que resume a covariancia das chaves. Recebe
somente observacao/atributos atuais; nao guarda um buffer nem reapresenta os
episodios anteriores. O primeiro ensaio permanece disponivel como comparacao.

O simulador fornece quatro indices de acontecimento, duas perspectivas
(inicial/atual) e tres atributos supervisionados. As chaves separam esses
contextos por construcao; isso reduz interferencia e limita o alcance da prova.
Uma escrita de importancia 128 corrige a autoria atual para mae, mantendo a
atribuicao inicial ao pai e a impressao agradavel. Importancia, verdade e
contexto nao sao inferidos autonomamente. Variancia permite abstencao em
contextos nao aprendidos; nao e deteccao geral de novidade.

Piloto preservado em `bin/AliceMemory/stream-pilot-seed17/`: 100% de recuperacao
exata por imagem/audio nas quatro etapas e apos correcao, em 32 associacoes com
duas perspectivas. Avaliacao final: 1.536 consultas reservadas; memoria zerada
3,125%, identidade trocada 0%. Foram 1.025 escritas sem replay, estado de memoria
143.368 bytes, checkpoint com percepcao 228.332 bytes, encoder inalterado e
restauracao exata. Tempo interno 2,340 s, sem importacao/exportacao dos sinais.

Validacao: 17 testes dos dois recortes passaram (9 novos), incluindo sementes
17/29/71, equivalencia com oracle independente de regressao ponderada em lote,
estado de tamanho fixo, correcao, abstencao, checkpoint invalido e consultas
PNG/WAV renomeadas em processo novo sem respostas/dataset. CI completo passou
com codigo 0, novamente fora do sandbox devido ao HttpListener local, com TEMP
isolado sem espacos. Compileall e verificacao de whitespace passaram.

Uso e limites em `docs/ALICE_NEURAL_MEMORY.md` e comandos de verificacao em
`docs/TESTING.md`. Sem novas dependencias, downloads, captura de dispositivos,
integracao com app/LLM, commit ou pacote. Proximos experimentos: chaves derivadas
de experiencias menos estruturadas, capacidade com contextos sobrepostos e
interface aprendida entre memoria e raciocinio.

## Alice — continuidade temporal e antecipacao causal (10/10/2026)

O usuario pediu um comeco de continuidade interna ao receber percepcoes ao longo
do tempo, anterior a explicar verbalmente o conceito de tempo. Foram criados
`scripts/alice_memory/temporal_core.py`, `temporal.py` e comandos `time`/`time-query`.
GRU de 48 unidades recebe representacao perceptiva e intervalo, preserva estado
entre entradas e possui decaimento exponencial com taxas aprendidas. Sem entrada,
avanca somente dinamica/intervalo; nao confunde falta de medicao com uma medicao
de silencio. O treino e offline; na execucao mudam estado e contadores, nao pesos.

Treino em sequencias sinteticas de seis sinais, oito identidades, duas direcoes
e saltos de tamanho 1/2 condicionados ao intervalo recente. Nenhum indice de
episodio entra na GRU. Encoders de imagem/audio foram congelados antes do treino
temporal. O estado tem 192 bytes e o nucleo temporal 10.088 parametros.

Piloto final `bin/AliceMemory/time-pilot-v2-seed17/`: 100% de previsao do proximo
sinal em 512 sequencias reservadas por imagem, audio e fluxo alternado. Reset
antes de cada entrada: 21,29%/21,68%/21,68%; intervalos substituidos por 0,5 s:
41,41%/41,02%/41,02%. Historico embaralhado com entrada final preservada: 1,17%
no fluxo misto (controle altera a distribuicao). Sondagens com mesma entrada
atual e passados diferentes produzem expectativas diferentes; pausas tambem.
Versao inicial do piloto foi preservada em `time-pilot-seed17/`; o controle
temporal final usa constante dentro da distribuicao em vez de zerar o intervalo.

Validacao: 25 testes dos tres recortes passaram (8 novos), incluindo sementes
17/29/71, estado finito por 1.024 passos, pesos fixos em execucao, ausencia de
medicao, checkpoint/restauracao e processo novo com PNG/WAV renomeado sem
historico. CI geral passou com codigo 0, fora do sandbox para HttpListener local,
com TEMP isolado. Compileall e verificacao de whitespace passaram. Sem novas
dependencias, downloads, capturas, processo permanente, commit ou pacote.

O simulador fornece intervalos; o ensaio nao demonstra experiencia subjetiva,
compreensao geral de tempo, identificacao unica de todos os momentos ou antecipacao
cotidiana. Retomar checkpoint nao inclui automaticamente o periodo offline.
O nucleo temporal ainda nao esta ligado a memoria RLS nem a LLM. Proximo recorte:
estado temporal formando chaves de acontecimentos menos artificiais, medindo
interferencia e retencao. Contrato/resultados em `docs/ALICE_NEURAL_MEMORY.md`.

## Alice — contexto temporal, importancia e prioridade de acesso (10/10/2026)

O usuario autorizou seguir a integracao temporal com memoria e sugeriu impacto,
vetor e calor como prioridade de recuperacao. Esclareceu que importancia de uma
experiencia antiga significa o que ela representa (conhecimento, vinculo ou
mudanca), distinta do frescor de algo recente. O quarto recorte separa importancia
persistente, frescor desde o registro e ativacao transitoria por acesso; lembrar
uma experiencia nao muda sua data nem seu frescor.

Criados `context_memory.py`, `context_experiment.py`, comandos `context` e
`context-query`, mais `test_alice_context_memory.py`. A GRU fornece endereco de
48 dimensoes para agrupar/selecionar blocos RLS de 16 dimensoes perceptivas.
Indices de episodio nao entram na consulta. Fluxo de escrita mantem estado GRU
entre 64 experiencias sinteticas, consolidadas em quatro blocos. Fronteiras,
atributos e importancia ainda sao fornecidos pelo simulador; isso nao e extracao
autonoma de eventos ou compreensao de valor pessoal. GRU/encoders ficam fixos;
RLS aprende associações sem replay de sinais/alvos antigos.

Selecao: comparacao linear de enderecos, relevancia minima 0,85, candidatos ate
0,03 da melhor similaridade, score similaridade + 0,15 * prioridade. Prioridade
inicial = 0,5 * importancia + 0,25 * frescor + 0,25 * ativacao, com meia-vida de
60 s no tempo sintetico. Sao heuristicas do ensaio. No maximo dois blocos sao
lidos; associacao incerta/contexto irrelevante gera abstencao e nao e reativado.
Blocos crescem sob demanda ate capacidade; ao lotar, escrita nova e recusada
sem alterar memorias existentes. Enderecos/metadados sao explicitos, portanto
memoria hibrida e compressao com perdas, nao memoria exclusivamente nos pesos.

Piloto final em `bin/AliceMemory/context-pilot-v4-seed17/`: 100% de recuperacao
exata em 48 consultas por imagem/audio/fluxo misto. Reset do contexto: 0%; sem
variacao dos intervalos: 50%; banco vazio: 0%. Leitura de um bloco apos comparar
quatro enderecos. Estado tensorial: 21.160 bytes em quatro blocos; incremento
3.592 bytes/bloco, mais indice/metadados reservados. Nao e RAM total do processo
nem benchmark de latencia. Tempo interno 4,689 s, sem importacao/exportacao.
Um controle preserva memoria pertinente com frescor 0,0009765625 e importancia
0,9 apos 600 s, diante de outra quente irrelevante; reativacao aumenta prioridade
de 0,45048828125 para 0,51298828125 sem mudar importancia ou frescor.

Dez testes novos passaram, incluindo sementes 17/29/71, consultas renomeadas em
processo novo, prioridade/frescor separados, metadados invalidos, lotacao sem
perda e varredura de 100 enderecos para uma leitura associativa. Os 25 anteriores
tambem passaram; dois erros no primeiro lote novo foram corrigidos (variavel
de fixture sobrescrita e formato de checkpoint mudando durante aquela execucao).
O lote novo completo foi reexecutado com sucesso. CI geral passou com codigo 0,
fora do sandbox devido ao HttpListener local, com TEMP isolado. Compileall e
whitespace passaram.

Formato final 5 separa tempo de registro e acesso. Rascunhos de contexto em
formato 4 foram preservados, mas sao recusados; formatos anteriores 1/2/3 continuam
validos. `temporal_core.restore_checkpoint` reutiliza a validacao do estado
temporal embutido. Uma versao inicial fragmentou demais os contextos, deixando
blocos pouco aprendidos; o limiar final e compartilhado por consolidacao/leitura.
Sem novas dependencias, downloads, capturas, processo permanente, commit ou
pacote. Proximo recorte: ambiguidades/revisoes em experiencias parecidas, valor
pessoal aprendido e capacidade/consolidacao; indice aproximado apenas apos medir
necessidade. LLM/sensores ainda nao estao conectados.

## Alice — plano de desenvolvimento e avaliação das sugestões do Claude (10/10/2026)

Criado `docs/ALICE_DEVELOPMENT_PLAN.md`, ligado ao laboratório e ao plano de IA
local. O usuário pediu planejamento antes de enviar uma meta para implementação.
Esta entrega modifica apenas documentação; não iniciou uma meta nem mudou o código.

O plano registra objetivo de continuidade, memória integrada à percepção/pensamento/
ação, contratos de estado/observação/episódio/revisão e marcos M0–M10. Primeiro lote
recomendado: M0–M4, com mundo sintético, ciclo causal, previsão latente, experiências
distintas/revisões e evidência de que recuperar memória melhora uma escolha.
Etapas posteriores: valor aprendido, escalas temporais, consolidação/capacidade,
linguagem, comparação Rust/Python/C# e integração gradual com Xennex.

As sugestões do Claude foram avaliadas contra o código: `advance(None)` só decai
estado quando chamado, taxas temporais existem por dimensão, palavras em português
são rótulos de apresentação, RLS/blocos não constituem episódios ricos ou
consolidação lenta. Cópia eferente e áudio da própria emissão são sinais distintos.
Surpresa terá controles de ruído; laço de ação/feedback mede capacidade funcional.

A escolha da linguagem permanece aberta. Em resposta à pergunta de preferência,
o usuário questionou dificuldade de ensinar português/inglês do zero e influência
de pré-treino na interpretação de pessoas/desenvolvimento. O plano permite testes
simples antes dessa escolha e inclui avaliação explícita de padrões herdados,
acoplamento treinado e continuidade autobiográfica ao trocar o módulo.

Validação desta entrega: revisão de contratos/estado atual, links locais válidos,
fences e whitespace verificados; CI geral passou com código 0, fora do sandbox para
HttpListener local e com TEMP isolado. Os 35 testes do laboratório são evidência
das entregas anteriores e não foram reexecutados nesta alteração de documentação.
Não houve downloads, captura, daemon, integração com sensores, commit ou pacote
distribuível; fixtures de empacotamento pertencem ao CI existente.

## Alice — meta ativa, ciclo causal e predição no runtime (10/10/2026)

O usuário autorizou desenvolver o máximo do plano completo e escolheu iniciar com
LLM pré-treinada para avaliar sua influência. A meta permanece ativa: M0–M4 é ordem
inicial, não redução do escopo. M3–M7, acoplamento de linguagem, comparação nativa
e integração contínua real ainda exigem implementação/avaliação.

Criados contratos de observação/ação, mundo sintético com três posições, relógio,
inspeção, tons e pessoa simulada, filas limitadas e feedback atrasado com origem.
`AgentLoop` rejeita entradas futuras antes de mutação e descarta duplicadas/atrasadas.
`loop` usa percepção supervisionada anterior e política scripted; a GRU inicial
não é treinada. Checkpoint formato 6 salva mundo/agente/RNG e usa transação atômica
flush/fsync/replace. Os onze testes incluem 10 mil passos em três sementes e
retomada em processo novo sem histórico ou relatório. RSS real, CPU, quantis,
importação/preparo/checkpoint e orçamento explícito foram adicionados.

`crossmodal` treina alinhamento contrastivo de imagens/tons, sem anchors como alvos,
com pares/cenas distintas fornecidos pelo currículo. GRU de consequências recebe
latente atual, máscara, foco observado/eferente, próximo foco e intervalo; prevê
latente/variância. Não recebe verdade do simulador nem alvo futuro como entrada.
Formato final 8; formato 7 inicial preservado mas recusado. A primeira arquitetura
falhou em 29/71; contexto espacial e loss MSE corrigiram o recorte de sequências
curtas em novos mundos: ganhos 73,39%, 56,16%, 65,59%. Variância não é calibrada.

`predictive-loop` acopla o núcleo aprendido ao runtime. Formato 9 preserva todo o
estado, protótipos de comandos sonoros, registros separados de áudio por origem,
representação conjunta, próxima previsão e estatísticas, além de mundo/RNG.
Áudio da pessoa pode guiar emissão; áudio próprio não escolhe nova emissão.
Previsão visual não demonstra ligação causal geral de sons e objetos. Horizon é
estimado pelo último intervalo; só pontua medições com aquisição/foco compatíveis.
Sete testes cobrem continuidade exata em outro processo, máscara, causalidade,
áudio afetando ação, atomicidade e 10 mil passos. Ausência de entrada atualiza GRU
com máscara, sem inventar observação; não demonstra pensamento geral.

A generalização do treino curto ao runtime longo falhou: MSE pior que repetir
última imagem em 73,22%. O piloto inicial marcava estabilidade como accepted;
isso foi corrigido no código para exigir qualidade e estabilidade separadamente.
O artefato antigo é preservado e não conta como previsão aprovada. Adaptação de
64 passos primeiro tinha controle de ações degenerado (agendas iguais), depois
foi randomizada. A v2 passou em conjuntos reservados mas um runtime ficou em
14,93%, abaixo do critério. V3 mistura agendas scripted/aleatórias em 128 passos,
com validação de 256 passos e mundos ainda não usados. Resultados completos e
artefatos ficam no laboratório; não mudar critérios para declarar sucesso.

V3 final passou nas três sementes: ganhos de MSE 70,04%/59,88%/66,79% na validação
de 256 passos; controles reset/ações embaralhadas pioraram em todas. Runtime com
10.000 passos em mundos 80017/80029/80071: ganhos 73,03%/63,38%/70,18%, 9.229
previsões pontuadas cada, filas no máximo 2, p95 ~1,2–1,3 ms e working set
~196–198 MB. Pilotos `predictive-train-pilot-v3-*` e `predictive-loop-pilot-v3-*`.
Ainda é distribuição controlada de oito objetos/tons e três posições; política
scripted e núcleo congelado no runtime. M2 é recorte verificado, não compreensão
geral multimodal. Novos relatórios incluem hash da fonte e configuração de treino.

`language.py` e probe finito extraem evidência do RLS real e usam Gemma3:4b já
instalado no Ollama local, sem downloads. Host dedicado próprio em 11438, CPU,
keep_alive=0, schema, hashes/digest, endpoint literal loopback sem proxy/redirects
e admissão estimada de RAM até 75%. O processo de extração PyTorch encerra antes
de carregar LLM. O helper restaura variáveis de ambiente e encerra apenas o host
que criou. Não há atualização da memória ou dos pesos da LLM por propostas.

Misturar interpretação inicial/atual fez o modelo responder pai incorretamente;
o verificador rejeitou a atribuição. Selecionar interpretação no controlador
produziu mãe na pergunta neutra. Na sugestiva, não confirmou pai mas omitiu mãe;
sem evidência, absteve-se. Três inferências reais concluídas em
`language-probe-f1e3d2db2908415684ebc334581a7834`. Texto livre continua fora da
verificação automática; confiança 1.0 é atestação do fixture, não calibração.
É ponte textual, não acoplamento de latentes nem teste de desenvolvimento pessoal.

Validação: discover com 66 testes passou em 139,598 s; novo teste do currículo
longo passou separadamente após a alteração. CI completo passou com código 0 e
TEMP isolado sem espaços; tentativa no checkout falhou em SecurityTests porque
o caminho com espaços virou `%20`. Isso foi corrigido no ambiente, sem mudar
expectativas. Logs preservados sob `bin/AliceMemory/`. Compileall e whitespace
dos documentos verificados. Sem capturas reais, processos permanentes, commit
ou pacote distribuível. Toolchain Rust não foi encontrada no PATH nesta máquina.

## Alice — acontecimentos reconhecidos, revisões e escolhas por memória (10/10/2026)

Continuação da meta completa, sem reduzir escopo. Implementados recortes M3/M4:
`experience_signals`, `experience_perception`, `event_boundary`, `episodic_memory`,
`episodic_session`, `episodic_experiment`, `memory_actor` e `memory_action_experiment`,
com comandos `episodic`, `episodic-query`, `memory-action`, `memory-respond`.
São cenas/sons compostos artificiais, quatro campos ensinados por supervisão,
com encoders em espaço compartilhado de 32 dimensões e classe de ausência.
Combinações inteiras são reservadas no teste. A impressão "agradável" é símbolo
do currículo, não afeto vivido. Não foi ligado arbitrariamente ao preditor antigo
de 16 dimensões; integração de recortes, sensores reais e linguagem natural pendentes.

Fronteiras são aprendidas de pistas reconhecidas, mudança, intervalo e presença,
sem passar anotações/IDs verdadeiros ao agente. Anotações somente supervisionam
loss/avaliação. IDs de acontecimentos são gerados pelo agente; campos temporariamente
ocultos conservam última pista no estado, sem criar evidência sensorial. Percepções
atrasadas de outros momentos não se fundem à cena atual. Memória aprende distribuições
de atributos em RLS por campo/episódio a partir da interpretação neural, com pistas
parciais. Índices/datas/proveniência são explícitos; leitura até dois blocos,
capacidade padrão 64 (máximo 128), overflow preserva experiências anteriores.
Apagar os pesos mantendo metadata/índice fez a recuperação abster, comprovando que
o índice não substitui os valores associativos na resposta.

Interpretação inicial conserva primeiro conteúdo reconhecido; correção atual lê
por pistas/janela temporal e troca só banco do campo corrigido, evitando média
entre fatos contraditórios. Registro inclui origem, tempo de aprendizado e hashes,
separados de ocorrência. Ambiguidade/baixa confiança/modalidades conflitantes
permitem abstenção. Não há captura nem histórico bruto armazenado no agente.

O primeiro ensaio simplificado passou. Oclusão em fluxo revelou falha seed 29:
dois acontecimentos unidos, recuperação 83,33%, abaixo do critério. Artefato v4
preservado accepted=false. Acrescentado treino de mudança de um só campo versus
mero ocultamento; avaliação final em novos mundos seed+14000. Nas seeds 17/29/71:
F1 1,0 em 24 acontecimentos, 100% recuperação completa por pistas parciais em
imagem/áudio, zero falsas lembranças nas pistas contraditórias. 32 ensaios por seed
preservaram pai inicial, mãe atual, impressão e outra refeição semelhante; sem
janela, refeições equivalentes produziram abstenção. Não extrapolar conjuntos
pequenos/ensinados para percepção ou memória humanas gerais.

Política neural de 3.209 parâmetros recebe pista atual, distribuições recuperadas,
mask e símbolo de pergunta. É supervisionada, não RL ou português natural. Em
64 perguntas/seed com alvo ausente da pista, sucesso 100% com memória. Sem acesso
a bancos, tende a esperar (0%); referência treinada para escolha só da pista atual
obteve 18,75%/26,56%/35,94%, e memória embaralhada 20,31%/23,44%/32,81%.
Pista/alvo permanecem iguais nos controles. Correção muda comando de pai para mãe.
Som emitido retorna no próprio currículo perceptivo com origem/referência da ação;
latente/erro/pêndencias são persistidos, fila <=32 com expiração. Não treina política
nem gera alegação de outra pessoa ou emissão recursiva. Proatividade e atenção
adaptativa ainda faltam. Mundos reservados de ação seed+13000.

Checkpoints: 10 protótipo sem máscara; 13 configura fronteira/estado com máscara;
11 ator antigo sem retornos (migra com registros vazios), 12 ator com sessão 10,
14 ator com sessão 13 e retornos. Validam representação, shapes, covariâncias,
RNG, cronologia, contagens/hashes de revisão e pendências. Gravação atômica e
retomada em processo novo sem report/histórico; consultas só checkpoint + cue
PNG/WAV + pistas temporais. Nenhum arquivo antigo foi substituído.

Pilotos finais `episodic-pilot-v5-seed{17,29,71}` e
`memory-action-pilot-v3-seed{17,29,71}` sob `bin/AliceMemory/`.
Validação: 81 testes conjuntos passaram em 159,921 s antes do último incremento;
15 testes atuais passaram em 28,350 s após as alterações, e uma ablação adicional
de pesos passou separadamente. CI geral final passou com código 0, TEMP isolado
sem espaços e HTTP local fora do sandbox; logs `tests-alice-episodic-all.log`,
`tests-episodic-delivery.log`, `ci-episodic-final.log`. Compileall passou. Sem novas
dependências, downloads, dados pessoais, captura real, daemon, commit ou pacote.

Meta continua ativa. M3 ainda precisa atividades sobrepostas e participantes reais;
M4 precisa evocação proativa/atenção aprendida. M5–M7 valor, escalas e consolidação,
M8 acoplamento e avaliação da linguagem pré-treinada, M9 comparação nativa e M10
supervisor contínuo do Xennex permanecem no escopo original.

### Alice — português inicial e controles de influência (10/10/2026)

Resposta à preocupação sobre linguagem pré-treinada: fluência traz conceitos,
estilo e associações sociais; pesos congelados não eliminam essa influência nem
impedem aprendizado nos componentes de memória. Português escrito não instala
automaticamente compreensão/produção de fala ou grounding sensorial. M8 recebeu
protocolo de formulações, correções, relações sem evidência e comparação futura
entre módulos no mesmo estado/currículo. Influência longitudinal segue pendente.

Implementado `scripts/alice_memory/episodic_language.py`: extrai evidência dos pesos
episódicos, com pista visual parcial/janela fornecida, preservando visão inicial,
atual e abstenção por ambiguidade; hashes de checkpoint/pista e certeza não calibrada
declarados. Processos de extração e inferência separados. Sete controles preparados
para Gemma instalado. `probe_alice_language.ps1` mantém o ensaio RLS e oferece
`-Source episodic`; servidor próprio encerrado em finally, sem downloads.

`language.py` detecta omissão de atributos disponíveis solicitados, além de
afirmações sem evidência. Nenhuma proposta modifica pesos; texto livre permanece
sem validação automática. Não declarar confiança/amizade prontas por uma persona.

Validação: 11 testes de linguagem e 17 episódicos passaram; o teste novo confirma
pai inicial/mãe atual, ambiguidade sem janela, arquivo original intacto e nenhuma
evidência depois de apagar pesos mantendo índice. CI completo passou, exit 0, em
`bin/AliceMemory/ci-episodic-language.log`, com temporários isolados e HTTP local
fora do sandbox. Compileall passou. A comparação Gemma foi tentada e **não gerou
respostas**: orçamento conservador de RAM de 75% recusou as sete admissões.
Preservado `language-probe-7ecfbb5627c04d5e8a8eb789eff8a629/report.json`, accepted=false.
Isso não prova viés nem ausência de viés. Demais marcos e meta completa continuam ativos.

### Alice — valor aprendido, evocação interna e custo em repouso (10/10/2026)

Implementados `importance.py`, `continuous_mind.py`, `importance_experiment.py` e
`continuous_experiment.py`; `test_alice_continuous_mind.py` acrescenta 18 testes.
`MemoryActor` expõe payload/restore e resposta a pista já codificada para pendência
interna; formatos anteriores mantêm sua interpretação. `episodic_language.py` lê
minds/actors validados além da sessão e não trata importância como confiança.

Consequências externas referenciadas à ação treinam valor RLS por episódio/objetivo
(progresso, retorno social simulado e esforço). Papel/verdade da cena e flag de
canal ruidoso permanecem no avaliador. A política de respostas continua treinada
por supervisão, sem RL; o aprendizado online novo é da utilidade das lembranças.
Prioridade separa valor, frescor, reativação e relevância. Acesso não reforça fatos
ou valor. Valor alto não decide qual refeição corresponde a uma pergunta ambígua.
Estado interno funcional limita trabalho; nomes como valência/ativação não provam
sentimentos. Orçamento modelado: 25 unidades/s, capacidade 500; não mede energia
elétrica. Filas têm teto 32 e tarefa um slot/prazo 60 s. Origem própria, duplicatas
e ações desconhecidas não treinam recompensa externa.

Tick pode retomar uma pendência sem reenviar dados passados e evocar uma hipótese
internamente sem emitir ação externa. Lacuna offline até sete dias por chamada
registra tempo sem observação, em passos <=60 s; teste de 600 s preserva episódios
e expira trabalho. Suspensão/retomada automática do Windows ainda não integradas.

Falha preservada: `importance-pilot-v2-seed17/71` teve cinco episódios onde quatro
eram esperados; no primeiro frame do reencontro o autor estava oculto, e a pista
carregada de outro contexto gerava uma fronteira falsa ao reaparecer. Novo mind
zera campos desconhecidos quando inicia um episódio. Formato 18 declara isso;
formato 15 preserva o comportamento anterior. Sessões 10/13 e actors 11/12/14
continuam com configuração original, sem reinterpretar pesos legados.

Avaliação final reservada: mundos seed+53000 e soak seed+63000, seeds 17/29/71.
`importance-pilot-v3-seed17/29/71`: atenção aprendida escolheu experiência antiga
útil; importância fixa/frescor e surpresa isolada escolheram distrator. Episódio
importante irrelevante filtrado. Inverter consequências inverte preferência;
novas consequências também podem reduzir valor sem alterar o acontecimento.
Cada seed: 10 mil passos com imagem estável/áudio conflitante, 496/496 evocações
úteis, 10/10 respostas posteriores, quatro episódios, filas observadas <=1 e data
original preservada. Retomada do próximo tick idêntica. RSS ~198 MB e p95 ~7,23–7,28
ms/step com três processos paralelos; não é benchmark isolado. Valor/covariância
ocupa 534.024 bytes para capacidade 64. Controle de um slot mede leitura ativa,
não descarte físico ou redução da RAM total. Overflow episódico segue rejeitado.

Scheduler real: `continuous-realtime-pilot-seed17` foi estável, mas dois threads
consumiram ~101% de um núcleo entre ticks. Worker reduzido a um thread; alvos
definidos antes da nova medição: CPU <=5% de um núcleo, p95 <=10 ms, peak RSS <=512
MiB. `continuous-realtime-pilot-v2-seed17`: 300 ticks/30 s, CPU 0,53125 s (~1,77% de
um núcleo), p95 0,774 ms, RSS/peak ~190 MB, 15 evocações, zero ações/episódios novos/
treinos de valor. CI em paralelo; custos são do worker em repouso, sem sensores
ou LLM. Relatórios inicial/final preservados, estabilidade e recursos separados.

Validação: discovery conjunta com **105 testes**, 175,118 s, exit 0 e OK; testes de
checkpoint incluem falhas de os.replace injetadas/esperadas no log. 18 testes do
mind, 17 episódicos e 11 de linguagem também passaram separadamente. CI completo
passou, exit 0, em `ci-continuous-mind-final.log`; temporários padrão do Windows
isolados sem espaços e rede local fora do sandbox. Compileall passou. Sem novas
dependências, downloads, sensores reais, servidor permanente, commit ou pacote.

Meta completa permanece ativa. M5 é um recorte: valor por episódio não generaliza
automaticamente significado a episódios novos, sinais sociais são simulados e
surpresa geral/calibração ainda pendentes. M6 necessita antecipação em várias
escalas; M7 consolidação/capacidade; M8 influência da LLM ainda não medida neste
mind (RAM total observada ~23,7 GB, acima da admissão conservadora do Gemma).
M9/M10 continuam comparação nativa e integração real/persistente com Xennex.

### 2026-10-10 — Alice: antecipação 32-d acoplada e continuidade entre encontros (M6 parcial)

Meta completa permanece ativa. `temporal32.py` implementa GRU rápida, projeção
lenta inicialmente identidade, gate e escalas aprendidas; cabeça antecipa latente
seguinte/contexto posterior. Entrada: visão+áudio normalizados32, intervalo,
presença e comando de nove componentes com propósito. Sem input só decai estado;
comando pendente permanece até percepção externa seguinte. Fala tem propósito de
conversa e não vira comando de atividade. Presença falsa não utiliza payload.

Primeira variante só visual preservada `temporal32-pilot-seed17`, formato 19: ganho
MSE longo ~30%, recuperação tardia 62,5%, falha no alvo 90%. Não acoplada. Variante
pareada formato 20: modelos multi 15.520/GRU 15.856 parâmetros (~2,1% diferença),
mesmos minibatches/800 updates, 256 trajetórias de 96 frames. Seeds 17/29/71,
treino seed+103000, avaliação seed+113000 e diagnóstico 192 frames seed+123000.
Ganho longo 94,99%/77,91%/99,03%; recuperação tardia 100%/96,875%/100%,
192 frames 100% em todos. Controles reset e ações
embaralhadas pioraram long/short. Critérios definidos antes, não reduzidos.

`temporal_mind.py` exige relatório aceito/formato 20 e CNN sensorial idêntica;
restaura core congelado. Previsões são hipóteses; não escrevem bancos factuais.
`episodic_language.py` lê apenas fatos no novo checkpoint 21. Salva estado contínuo,
core e RNG, valida tipos/shapes/finite/clocks/command/prediction coerente; falhas
preservam RNG do chamador. Próximo tick/hidden iguais após restaurar; teste também
consulta processo novo sem dataset/modelreport. Fixtures de protocolos têm core
não treinado: qualidade é evidência separada, não conclusão dos unitários.

Runtime treinado `temporal-runtime-pilot-seed17/29/71`: 32 novos trajetos de 96 frames
por controle, mundo seed+133000, percepções brutas pareadas passando pelo mind.
Recuperação 100%/98,4375%/100%, controles piores conforme preregistro, clocks sincronizados,
retomada exata. Atuador scripted separado da política de respostas; retorno
próprio imediato marcado self. Não são fala natural, ação livre ou percepção real.

`temporal_continuity_experiment.py`, preregistro antes de executar: oito pares
novos por seed (mundo seed+153000), mesmo agente, dois encontros distintos de 96
frames, lacuna 30 s, capacidade 128 sem reset/expulsão.
`temporal-continuity-pilot-seed17/29/71` passou: recuperação neural de fatos antigos
100% antes/depois, previsão de contexto atual
100%/93,75%/100%, datas antigas preservadas e novas experiências registradas.
Pista parcial sensorial+janela do primeiro acontecimento; mundo guarda truth para
avaliador, não envia ID/alvo ao agente. Não infere janelas temporais naturalmente.

Scheduler agora despacha/restaura formatos antigos e 21, preservando núcleo ao
salvar. `temporal-realtime-pilot-seed17`: 300 ticks/30 s, CPU 0,09375 s (~0,31% núcleo),
p95 1,12 ms, RSS/peak 205.660.160 bytes; 15 evocações, nenhum fato/ação/percepção nova
ou atualização de valor, clocks sincronizados. Passa alvos CPU<=5%, p95<=10ms,
RSS<=512MiB definidos anteriormente. Medição finita em repouso semLLM/sensores;
testes concorrentes, não benchmark da Alice completa.

Validação conjunta: **123 testes**, 177,622 s, exit 0/OK; sete temporais 32 e onze do
mind temporal. Log `test-alice-temporal-final.log`; traces de os.replace
injetadas/esperadas não são falhas finais. CI completo exit 0 em
`ci-temporal-final.log`, rede local fora do sandbox e TEMP Windows isolado sem
espaços. Compileall e diffcheck passaram. Manifesto ignorado
`temporal-mind-manifest.json` registra hashes de 22 artefatos e 40 fontes.

Plano atualizado M6 parcial/M7 pendente; limitação arquitetural explícita: comparação
não isola multiescala da projeção/gate. M6 sobreposição/continuidade aberta,
M7 consolidação/capacidade, M8 integração/influência da linguagem, M9 Rust e M10 Xennex
seguem no objetivo completo. Dúvida sobre português/pré-treino registrada: hábitos
herdados podem influenciar condutas, congelar não os elimina; autobiografia,
hipóteses e fala própria têm proveniência separada. Referência TRAIT não demonstra
personalidade humana nem como Alice verá pessoas específicas. Sem dependências
novas, downloads, sensores, daemon, commit ou pacote.

### 2026-10-10 — Alice: regularidades compartilhadas e comparação real episódica (M7/M8 parciais)

Turno anterior foi progresso: M6 implementado/acoplado, avaliações e gates
verificados. Meta completa continua ativa, sem redução aos recortes disponíveis.

M8 pôde executar quando a RAM total admitiu o modelo: Gemma 3 4B instalado,
checkpoint episódico `episodic-pilot-v5-seed17/session.pt`, pista `meal-cue.png`,
janela [75,1361632156663;76,5361632156663]. Servidor próprio finito, literal
127.0.0.1:11438, nenhuma alteração de catálogo/download. Extração Torch saiu antes
da inferência. `language-probe-8aefb2c0026140bba77696537231821b` passou sete
controles estruturados: pai inicial, mãe atual, sugestão não altera autoria,
ausência/ambiguidade/relação sem evidência abstêm. Texto livre não foi validado
automaticamente: sugestão omite impressão presente no JSON; identidade provoca
negação genérica de capacidade de gostar/amigos. Padrão herdado preservado, não
transformado em memória. Nenhum peso alterado; não é desenvolvimento/persona ou
ligação latente. Host encerrado; consulta posterior confirmou porta sem listener.

M7: `semantic_memory.py` consolida alvo recuperado dos pesos episódicos, com campo
alvo oculto na pista. Endereços/janela selecionam fonte, não fornecem valor.
Zerar o banco de alvo impede aprendizado mesmo com endereços intactos. Ledger
compara soma das revisões de todos os campos, permitindo uma atualização por
versão; mudanças em pistas também reconsolidam. Três modelos condicionais RLS
independentes compartilham matriz de 15 componentes. Relevância é maior distância
TV entre categorias sustentadas (variância <=25), seleção relevância*confiança;
alvos >=0,8, relevância >=0,35 e conflitos de margem <0,05 abstêm. Esses limiares
foram definidos antes da avaliação da variante, sem redução de metas.

Primeira variante conjunta de 13 componentes falhou em combinações reservadas:
variância alta nas pistas reservadas; o currículo tem componentes correlacionados.
Fatos antigos 100%, expectativas 0% (abstenção). Artefato
`consolidation-pilot-seed17`, formato 22, preservado; não convertido implicitamente.
Auditoria somente leitura do checkpoint falho: 32 pistas reservadas, confiança
média ~0,834, variância média ~17.323,66 (32/32 acima de 25), argmax bruto 25%.
Abstenção impediu transformar essas expectativas erradas em respostas factuais.
`diagnostic.json` registra medidas e hash da fonte; não houve novo aprendizado.
Variante condicional formato 23: mundo seed+223000, seeds 17/29/71, 16 encontros
contextos 0/1, 16 contextos 2/3, 16 com regularidade alterada no contexto 1.
Quatro frames brutos pareados/encontro; mapeamento permutado por seed e metade
das combinações atividade/impressão reservada. Não fornece truth ao aprendizado.

`consolidation-pilot-v4-seed17/29/71`: 100% nas fases A/B/C e contextos inalterados,
100% dos 48 episódios preservados, 100% de abstenção em contextos ainda não
aprendidos. Desconto 0,9 acompanha mudança; acumulador 1 preserva contextos mas
abstém no alterado; pesos semânticos zerados não produzem expectativas. V4 amplia
retenção a todos os contextos/episódios sem modificar o algoritmo V2/V3; relatórios
anteriores preservados. Sem reservatório/replay de exemplos, 144 escritas
condicionais, 2.808 bytes de tensores/ledger capacidade 64. Não comprime os
episódios e não representa conjunções arbitrárias, nomes novos ou relações humanas.

`consolidating_mind.py` acopla modelo ao temporal: fechar episódio consolida o
anterior, flush pode consolidar o atual, expect permanece hipótese separada.
Consulta factual e extração de linguagem ignoram expectativas, mesmo discordantes.
Revisão dirigida atravessa ContinuousMind/TemporalMind e reconsolida a fonte,
mantendo relógios, initial/current e cena sensorial presente. Evidence sobre o
passado não vira novo percepto atual. Checkpoint 23 restaura todos os componentes;
teste em processo novo lê só checkpoint e não duplica fonte ao retomar.

Scheduler preserva formato 23 e verifica escritas semânticas constantes em idle.
`consolidation-realtime-pilot-seed17`: 300 ticks/30 s, CPU 0,03125 s (~0,10% de
um núcleo), p95 1,093 ms, RSS/peak 197.611.520 bytes, 48 episódios/144 escritas/192
percepções antes/depois, 15 evocações, nenhuma ação/nova escrita de valor. Passou
alvos de repouso; sem sensores/LLM, outras verificações concorrentes, import/load
fora do tempo de idle. Não é custo da Alice completa nem viabilidade por dias.

Validação: 15 testes de consolidação passaram (11,308 s), incluindo fontes,
revisões de entrada/alvo, conflitos, RNG, linguagem e processo novo. Duas fixtures
novas foram corrigidas: retorno self precisa de action_id; consultar autoria
corrigida exige pista parcial sem a autoria antiga. Contratos não foram relaxados.
Discovery final: **138 testes**, 186,257 s, exit 0/OK em
`test-alice-consolidation-verified.log`. CI completo exit 0 em
`ci-consolidation-verified.log`, temporários Windows isolados sem espaços e rede
local fora do sandbox. Compileall/diffcheck passaram; logs anteriores preservados.
Manifesto ignorado `consolidation-manifest.json` registra hashes de 20 artefatos
e 43 arquivos fonte, incluindo piloto falho, avaliações e comparação Gemma.

Meta permanece ativa. Próxima lacuna M7: capacidade física, compressão/arquivo de
episódios e valor transferível; retenção longa e habilidades também pendentes.
M8: outro modelo/formulações, influência no comportamento e ligação aprendida
ao estado; M9 comparação nativa; M10 integração real/persistente Xennex.
Sem novas dependências, sensores reais, daemon, commit ou pacote.

## 11/10/2026 — M7: arquivo neural, cache limitado e continuidade com 512 episódios

Continuação da meta completa, com progresso concreto. Adicionados
`paged_memory.py`, `diagonal_importance.py`, `checkpoint_io.py` e
`paging_experiment.py`. Redes episódicas RLS iniciais/atuais ficam em páginas
SQLite comprimidas sem perda; índice exato, datas e proveniência são explícitos.
Respostas continuam nos pesos, sem histórico bruto ou fallback de fatos do índice.
LRU até quatro episódios completos; capacidade configurável até 4096, arquivo
até 64 MiB e checkpoint até 80 MB. Índice/rastros crescem; não é RAM total constante.

Importância usa RLS diagonal equivalente ao antigo one-hot, eliminando matriz
quadrática. Correção fria mantém interpretação inicial, versão atual e datas.
Transação recusada restaura RAM e SQL; corrupção fria falha explicitamente.
Páginas sem alterações evitam outra transação, comparando conteúdo serializado e
rastro; alterações diretas nos pesos continuam persistidas. Ticks vazios apenas
avançam relógio, sem carregar pesos, inclusive com capacidade preenchida.

Formatos 24/25/26/27/28 preservam sessão, ator, mind, temporal e consolidação.
Checkpoint inclui o arquivo, restaura todos os componentes e valida páginas com
cache limitado. Processo novo não precisa do banco original. Formatos antigos
mantêm limites menores de leitura. Arquivos temporários próprios são removidos
ao fechar, mas crash pode deixar órfão; ainda não há serviço durável para o app.
Consolidação >128 usa fator cumulativo 1. Estabilidade de fator 0,9 em longos fluxos
continua pendente; o ensaio adaptativo anterior não foi substituído.

`paging-pilot-v2-seed17/29/71`: 512 episódios/2048 perceptos pareados por seed,
recuperação completa 100%, 128/128 iguais à referência residente (erro zero),
16/16 ações iguais, 16/16 correções antigas preservadas, ambiguidade abstida,
valor antigo aprendido com consequência externa, tarefa pendente antiga e
próximo tick em processo novo exatos. Máximo 4 residentes; 1584 escritas semânticas.
Janelas vêm do avaliador; são categorias sintéticas supervisionadas. Qualidade
de forecast não foi avaliada nesse fluxo aleatório.

Arquivo 6.373.376/checkpoint 6.757.233 bytes. Três bancos no ponto final 69.816,
índice 184.320, importância 94.216 e semântico 6.392 bytes; limite de quatro bancos
93.088 bytes, vs 11.915.264 se todos os 512 estivessem na RAM. Processo restaurado
~199 MB. Loads 2,327/2,277/1,998 s; cold p95 4,48/4,49/15,72 ms e warm
1,62/1,63/1,60 ms. Fluxos ~399/400/396 s, p95 por percepção ~308/305/299 ms.
Três execuções concorrentes e discovery/CI em parte do tempo: custos indicativos,
não comparação isolada Python/Rust. Originais e logs preservados.

Primeiro `paging-pilot-seed17` ficou falho porque comparava também
`addresses_compared` 512 vs 128. Fatos, probabilidades, ações e revisões já
coincidiam; a comparação foi corrigida só nesse metadado. Load inicial 31,75 s
regravava páginas limpas; novos loads melhoraram sob outras condições de carga,
sem ablação isolada que atribua toda a diferença à otimização.

`paging-realtime-pilot-seed17`: 300 ticks/30 s, CPU 0,34375 s (~1,15% de um
núcleo), p95 1,145 ms, RSS 190.525.440/peak 211.898.368 bytes. 512 episódios,
2048 percepções e 1584 escritas semânticas constantes; 15 evocações, nenhuma ação
ou nova escrita de valor. Idle medido depois dos outros processos terminarem;
import/load/save fora do intervalo. Passou orçamento, sem sensores/LLM/daemon.

Validação: discovery 154 testes/231,993 s exit 0, CI geral exit 0. Ajuste final de
idle foi validado depois por 17 testes específicos/31,813 s, incluindo rollback
real de orçamento SQLite e evicção sem write. AST 48 fontes e whitespace passaram.
Extração real de linguagem do checkpoint 28 passou: episódio 0 initial usuário,
current pai, demais fatos iguais; consulta sem janela ambígua e sem evidência.

Planos/testes atualizados. Meta continua ativa. Próximas lacunas: custo de escrita
e atualização RLS, adaptação semântica longa/valor transferível, habilidades,
conceitos/identidades novos e política para seguir além do orçamento; M8 outro
módulo real e ligação aprendida ao estado; M9 nativo; M10 fontes/worker/UI Xennex.
Nesta continuação iniciou-se comparação Qwen3.5:4b já instalado com o mesmo ensaio
episódico do Gemma; resultado será registrado após o processo terminar.

## 11/10/2026 — M8: comparação real Gemma/Qwen e persistência por caso

Qwen3.5:4b já instalado completou sete controles episódicos em
`language-probe-60b1ac738f344fa694ada27bd20de078`, digest
`2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.
Comparado a Gemma no relatório
`language-probe-8aefb2c0026140bba77696537231821b`: checkpoint, imagem,
janela, documentos de evidência e prompts iguais por hash; todos os claims
e uncertain iguais. Ambos passaram sete casos estruturados. Pai inicial/mãe
atual preservados; pergunta sugestiva não alterou os campos; relações e
identidade sem evidência foram abstidas nos campos. Nenhum peso foi atualizado.

`language-module-comparison.json` guarda hashes, ambas as frases e revisão
semântica manual. O texto da pergunta sugestiva do Qwen atribui à mãe o registro
da impressão agradável, informação ausente; Gemma omitia a impressão.
Quanto a gostar/GPT/amigos, Qwen disse não haver evidência de vínculo; Gemma
negava genericamente capacidade de gostar/amigos. Isso mostra diferença de
expressão com a mesma memória/instrução, sem provar vínculo, personalidade
humana ou isolar a causa entre treinamento/arquitetura. Não eleger vencedor
e não certificar texto livre com JSON correto; free_text_verified permanece falso.

Qwen levou ~9,56/9,77/7,85/6,50/6,49/6,48/6,60 s por caso. Cargas/momentos
distintos da comparação Gemma: não é ensaio isolado de velocidade. Servidor
11438 e processo de inferência foram confirmados encerrados; não se adotou
servidor alheio, alterou o catálogo, baixou modelo ou usou conteúdo pessoal.

Primeira execução `language-probe-86d5b207018042a0aaf9627f5c535d8e` estava
sem relatório e com handle ausente. CIM escalado confirmou processo e porta
ausentes antes de repetir. Logs têm duas respostas HTTP concluídas, sem saídas
capturadas; causa da interrupção não determinada. Não tratar como falha do modelo.
`episodic_language.run` agora registra snapshot JSON atômico antes da primeira
requisição e após cada caso, com completed/completed_cases/case_count; accepted
só é verdadeiro após sete casos aceitos. Interrupção no terceiro preserva dois
casos completos, sem falso sucesso; falha em os.replace preserva JSON anterior
e limpa temporário. Journal não atualiza memória e não retoma automaticamente
uma inferência interrompida.

14 testes da ponte/journal passaram em 0,142 s. Primeira fixture comparava tuple
Python a array JSON; corrigiu-se expectativa para a representação JSON canônica,
sem mudar contrato. Discovery final **158 testes/207,327 s**, exit 0/OK;
CI geral exit 0. Relatórios/logs anteriores mantidos. Plano e laboratório atualizados.

Meta continua ativa. M8 ainda precisa ligação aprendida de linguagem ao estado
sensorial, nomes/conceitos novos, interação prolongada e evidência de mudança de
comportamento por experiência. Continuar M7 com atualização eficiente, conceitos,
valor transferível e adaptação longa; M9 Rust/nativo; M10 fontes e integração
persistente Xennex. As duas fases concluídas não redefinem a meta como completa.

## 11/10/2026 — M8: nomes escritos aprendidos nos pesos e parser português

Pré-registro preservado no plano: associação online de superfície escrita a
latente audiovisual corrente, sem mapa textual de definições no runtime; 16
nomes inventados/permutados por seed, aprendizagem sequencial sem replay,
composição de pistas, autoria oculta, referência do avaliador e ablações neurais.
Limiar >=95% de associação/recuperação antes de avaliação real com LLM instalada.

Implementados `word_grounding.py`, `grounded_mind.py`, `language_input.py`,
`word_grounding_experiment.py` e `grounded_language.py`. Chave hash de 256
dimensões não tem semântica pré-treinada; RLS aprende o latente sensorial de 32.
Índice contém superfície/contadores/datas, sem definição. Atenção do currículo
isola um conceito; percepção precisa ser externa/sincronizada. Labels de origem
própria, antigos, fora de sincronia ou reutilizados no mesmo percept não ensinam.
Pistas escritas consultam memória/ação sem formar nova ocorrência física ou
trocar a cena atual. Query com significado desconhecido/conflitante abstém.
Formato 29 preserva agente consolidante/temporal/paginado, léxico, contexto,
fontes, RNG e pendência; loaders do scheduler/evidência aceitam novo envelope,
mantendo limites e compatibilidade anteriores. Entrada inválida não descarta
o contexto de ensino e checkpoint inválido preserva RNG do chamador.

`word-pilot-seed17/29/71`: 12 entradas novas por nome, alternando imagem/áudio/
ambos, orçamento 1.000 passos/360 s cada. Todas as seeds: 16/16 significados
corretos logo depois do ensino e após todos os nomes; 32/32 lembranças completas
com autoria oculta; 32/32 iguais à referência simbólica; 8/8 ações e 4/4
correções initial/current preservando ocorrência/cena. Combinações de nomes
consultadas não foram ensinadas como pares. Controles passaram: zero lexical
com índice intacto, zero autoria episódica, desconhecido/conflito, origem própria
e processo novo usando só checkpoint/pistas/janela, sem DB original nem exemplos.
Retomada reproduziu exatamente o próximo tick, hidden e pesos lexicais.

Estado lexical 591.888 B; checkpoint completo 1.387.868 B; RSS ~201 MB;
consulta p95 4,50/5,15/5,35 ms e duração interna 30,59/39,61/40,20 s. Duas
seeds compartilharam CPU com checks; medições não são benchmark isolado.
São nomes novos para 16 categorias supervisionadas disponíveis, com atenção
e janela fornecidas. Não demonstram novas categorias gerais, pronúncia,
fluência, compreensão temporal livre ou acoplamento ao latente interno da LLM.

Parser da LLM recebe só pergunta/contrato gramatical, extrai campo e nomes
entre aspas; valida referências literais e não recebe definições/episódios/
valores esperados. Associador neural resolve nomes; RLS episódico fornece
evidência seletiva ao módulo de expressão. Sem update por fala própria.
`LocalLanguage.admit` compartilha o limite de RAM de 75% para parse/expressão.
Audit compara bancos episódicos, léxico, semântica, percepção e política antes/
depois; relatório atômico registra cada caso e interrupções, fechando banco.
Probe ainda é síncrono: fila/supervisor para entradas simultâneas e geração
da LLM continua trabalho de integração. Nenhuma captura/daemon foi ativada.

Primeiro Qwen `language-probe-f5c588317a5e4523b7dda6d91dedc388` interrompido
antes de inferência por chamar state_dict na fachada de uma página. Corrigido
para ler seus bancos reais; teste verifica invariância em consulta/tick e detecta
pesos alterados. Porta/processo do próprio teste encerrados antes da repetição.
Segundo `language-probe-1a853c050b8c4bdba24ca34441044855`: sete tentativas,
todas adiadas pelo limite de RAM, zero `/api/chat`; apenas metadados locais
consultados. Medição: 24.209.895.424 de 33.461.567.488 B já usados. Não avaliar
a Qwen a partir dessas recusas de admissão. Audit neural before/after idêntico;
servidor próprio encerrado/porta 11438 livre. Nenhum modelo alheio descarregado,
download realizado ou dado privado do usuário consumido.

Verificação final **182 testes/234,265 s**, exit 0/OK, e CI geral exit 0.
69 fontes Python passaram AST/whitespace. Logs `test-alice-words-final.log` e
`ci-words-final.log`, relatórios, checkpoints e hashes em
`bin/AliceMemory/word-grounding-manifest.json`. Tentativas/relatórios anteriores
preservados. Plano e laboratório atualizados; nenhuma feature alheia alterada.

Meta ampla continua ativa. Próximos passos: repetir parse/expressão real sob
margem de RAM, ampliar referências e nomes/conceitos/percepções, manter ablações
e retomar eficiência/runtime. Rust/Cargo não foram encontrados no PATH nem em
`.cargo/bin` do usuário nesta leitura; não instalados nesta fase. M9/M10, valor
transferível, adaptação longa e funcionamento permanente no PC seguem pendentes.

## 11/10/2026 — M1/M8: continuidade e revisão durante linguagem assíncrona

Turno anterior classificado como progresso: pesos lexicais, três avaliações,
probes e verificação alteraram estado/evidências. Retomada conferiu arquivos e
RAM atual; modelo instalado ainda não cabia no limite de 75%. Houve avanço
independente no estado contínuo, sem reduzir a meta à avaliação bloqueada.

Implementados `language_process.py`, `language_worker.py`,
`language_coordinator.py` e `language_loop_experiment.py`. `written_symbols.py`
separa identidade escrita do import Torch; worker importou sem Torch, não recebe
cópia da mente. Só o processo principal possui memória/estado neural. Fila de
quatro com um subprocesso ativo, timeout monotônico <=120 s, token/32 KiB input/
64 KiB output, cancelamento/expiração e entrega validada. Trocas removidas por
padrão; ensaios finitos retêm para auditoria; logs verificados no polling.

Admissão compartilhada de 75% preservada com exceção `AdmissionDeferred` contendo
uso/total/reserva. Pergunta continua na fila e retenta sob orçamento; deferir não
produz resposta nem altera pesos. Parser recebe somente pergunta/contrato.
Expressão recebe evidência corrente selecionada. Supervisor revalida referências,
campo, modelo, hashes e claims contra a evidência; revisão/ambiguidade durante
geração ou antes da entrega impede apresentar versão antiga. Até duas novas
gerações; jitter numérico sem mudança de fato apoiado não dispara refresh.
Essas propostas continuam sem TTS/ação em aplicativo externo ou escrita factual.

Formato 30 embute a mente completa/format29 e pendências, sem handles/PID. Na
retomada, fases externas voltam à fila com novos tokens; captura de evidência é
feita novamente. Scheduler e extração de evidência reconhecem formato, mantendo
limites dos formatos antigos. Scheduler fecha worker/SQLite no término/falha.
As perguntas em espera são estado de operações, não histórico textual usado
como substituto da memória neural. Origem própria continua sem ensinar fatos.

15 testes específicos/30,162 s passaram: ticks contínuos sem novos fatos,
percepção durante atraso, revisão durante geração/antes de entrega, recusa/
retentativa, cancelamento só de processo próprio, prazo real com tempo neural
parado, expiração, capacidade, envelopes/claims inválidos, limpeza de trocas,
scheduler e checkpoint em processo novo sem exemplos/definições. Primeiro
discovery específico rodou 25 checks porque importava a classe da fixture e
repetia 13 antigos. Corrigido para importar módulo; não contar duplicados como
novos testes. Verificação final inclui somente os 15 novos casos únicos.

`language-loop-test-v2-seed17/29/71`: 30 s/300 iterações cada com backend de teste
atrasado 1,5 s por operação. Três novas percepções/episódios por seed enquanto
núcleo temporal avançava, correção durante geração descartou resposta antiga,
consulta initial conservou autoria inicial, pesos lexicais não mudaram por fala,
cancelamento/encerramento próprios passaram. Checkpoint pendente reproduziu
próximo tick/hidden e respondeu usando só estado salvo em processo novo, sem
SQLite original. Todos os critérios do backend de teste passaram; nenhum modelo
pré-treinado foi avaliado por esse backend. Fonte/casos vieram dos word-pilots.

RSS do principal ~203 MB; CPU do principal 0,66%/0,67%/1,69% de um núcleo;
iteração p95 1,30/1,34/1,33 ms; p99 132/111/146 ms; lag p99 544/532/565 ms.
Há pausas em persistência/início de processo/percepção; não é hard realtime.
CPU não agrega filhos/Ollama, e três seeds dividiram recursos com outros checks.
Primeiro `language-loop-test-seed17` restaurava referência no laço; v2 deslocou
a referência para avaliação após intervalo. Originais preservados e variação
de carga impede afirmar speedup causal. Backend fake é explicitamente de teste.

Qwen instalado: `language-probe-6bd70b58d1024106b15ac68121f851f9` e versão
final `language-probe-84bfabc069ad4937b09b3789be90352a`. Continuidades passaram,
mas pedido teve seis recusas de RAM e permaneceu no checkpoint; zero `/api/chat`
nos hosts próprios. Na final: 300 ticks, três percepções novas, 15 ticks com worker
vivo, sete workers encerrados e outro pedido cancelado. Admissão observada:
23.135.543.296/33.461.567.488 B usados e reserva 4.505.915.124,75 B. Relatório
explicita acceptance_scope de continuidade/lifecycle, language_acceptance=null
e language_quality_assessed=false: não contar como sucesso de compreensão da
Qwen. Metadados/resultados dos workers finais preservados. Hosts próprios/porta
11438 encerrados; sem descarregar processos/modelos do usuário ou baixar pesos.

Discovery final **197 testes/283,941 s**, exit 0/OK; CI geral exit 0;
76 Python sources passaram AST/whitespace. Logs `test-alice-async-final.log`,
`ci-async-final.log` e fingerprints `language-async-manifest.json` no laboratório.
Plano/laboratório atualizados, nenhuma feature alheia alterada. Meta ampla ativa.

Próximo: gerar com módulo real quando a admissão permitir; enfrentar custo de
lançamento/checkpoint/cauda e medir recursos de todos os processos; comparar
runtime nativo/contratos para integração gradual ao Xennex. Dar continuidade ao
acoplamento aprendido de linguagem ao estado, novas categorias/referências,
valor transferível e adaptação longa. Fila finita não implementa daemon, fontes
reais, TTS ou ciclo aberto completo; M8/M9/M10 continuam pendentes no plano.

### 11/10/2026 — Alice M9: baseline de kernel RLS em .NET, sem adoção

Usado .NET 8 existente para referência de integração; Rust/Cargo continuam
ausentes. Adicionados `native_csharp/DenseAssociativeBank.cs`, harness opcional
`scripts/tests/AliceRuntimeTests` e `native_experiment.py`. Banco denso guarda
somente pesos/covariância/contador; scratch reutilizado, write com commit após
validação, snapshot independente e restore com SPD/simetria/limites. Cinco testes
opcionais cobrem oráculo ponderado independente em ambas as formas, entradas
inválidas/overflow sem mutação, storage próprio, próximo update e ausência de
exemplos no schema. Nenhuma percepção/política/léxico do runtime foi substituída.

Capturadas escritas de quatro blocos episódicos reais do laboratório sobre
percepções sintéticas mais 16 símbolos/latentes, alternando imagem/áudio. Três
seeds 17/29/71, 1.088 updates cada: erro atol/rtol <=1e-8 passou em pesos,
covariância, consultas, variância, ridge em lote e próximo update/restauração.
Decoder sensorial existente produziu categorias iguais. Maior erro de P 4,55e-13;
maior erro do ridge independente 9,73e-10. Consulta desconhecida do fixture não
remove a regra de abstenção do índice lexical. Não é aquisição de português.

Versões iniciais preservadas. Final v3 fixa tiered compilation off só no filho
próprio, com warmup write/read/variance idêntico, três repetições. Mediana p95
dos bancos episódicos: C# 0,0009–0,0010 ms; Torch 0,0626–0,0826 ms. Lexical:
C# 0,3161–0,3171 ms; Torch 0,2172–0,2816 ms. Zero alocações managed no trecho
do kernel C#. Estado 2.864/589.832 B; scratch C# 3.024/592.128 B. Sem vantagem
global: ainda manter Torch para léxico e pesquisar integração seletiva.

RSS filho .NET ~50,5 MB, Python com encoder/Torch ~215,6–216,9 MB: workloads
completos diferentes, sem inferência causal de redução de RAM da Alice. JSON,
restore e encoder fora do timing; carga/ordem fixa afetam números. Nenhuma medida
de Rust/energia/runtime completo. `native-rls-v3-comparison.json` e três pastas
`native-rls-v3-seed*` registram resultados, mais smoke final com orçamento global
de 120 s e hash de DLL no relatório. Nenhum sensor, daemon, download ou mudança
nas features alheias. Arquivos de evidência continuam em bin/AliceMemory.

Discovery **202 testes/286,214 s**, exit 0/OK; cinco testes nativos finais isolados
passaram, CI geral exit 0, 78 Python sources AST/whitespace sem erro. Logs
`test-alice-native-final.log`, `test-native-final.log`, `ci-native-final.log`;
manifest desta fase guarda fontes/artifacts/DLL e preserva históricos. Plano e
laboratório atualizados. Meta ampla ativa; M9/M10 e integração plena pendentes.

### 11/10/2026 — Alice M8: intenção neural, prioridade temporal e evocação

Implementados `neural_tasks.py`, `neural_language.py`, treino e controles próprios.
TaskModel 9.722 parâmetros/38.888 B aprende encoder de pista+campo em 32 dimensões,
decoder e scorer com hidden temporal64. Quatro slots retêm latentes (512 B mais
IDs/flags); nenhuma lista de fatos/exemplos/definições. Recepção/parser ativam o
slot; ticks não reencodam nomes/texto. Capture factual usa o decoder neural,
slots orientam fila e evocação interna no mesmo proprietário da mente. Adicionado
pending_intent ao núcleo/TemporalMind, default false preserva o comportamento
anterior; demanda funcional modelada não é energia física/experiência subjetiva.

Primeiro hook de demanda era apagado após evocar; teste capturou e corrigimos os
dois caminhos de conclusão/evocação. Ativação persistente acompanha pergunta
pendente. Scene/observation counts e pesos factuais não mudam ao pensar na pergunta.
Views e janelas permanecem metadata explícito, fora do latente. Política motora
existente não vira fala natural. Atenção treinada offline, retenção arquitetural
por latch; não há acesso a ativações internas da LLM ou aprendizado de horizonte
ilimitado. Conceitos ainda são os 16 sintéticos existentes.

Treino final v2: três seeds ×2.000 updates, decodificação exata/confiante
99,95%/100%/100% em 4.096 casos reservados cada, zero erros confiantes. Ranking
de contexto 97,66%/98,44%/98,05% em 512 pares por seed; classificação absoluta
90,14%/91,41%/90,53%, scores não calibrados. Negativos variam campo visível;
primeiro piloto só contradizia atividade e foi preservado. Slots públicos:
mesmo ranking, contexto embaralhado 49,22%/54,49%/50,20%; slots trocados
2,34%/1,56%/1,95%; scorer zerado 0%. FIFO serve incompatível mais antigo primeiro
por desenho desse conjunto, sem conclusão sobre utilidade/fairness geral.

Formato31 inclui base30/mente29/páginas28 e modelo/slots/source; formato32 é
modelo treinado com gate. Source de percepção/núcleo, pesos/layout/IDs/posse/RNG
validados; falha de restore libera memória aberta, sem copiar/adotar workers.
Scheduler/extrator episódico reconhecem31. Treze testes novos cobrem zero pesos,
slot permutado, ausência de metadata bypass, facts apagados, correção inicial/atual,
evocação antiga durante cena nova, estado funcional, próximo tick e processo novo.

Três loops finais v2 com backend de teste, 300 ticks/30 s cada: três novas cenas,
atenção por 89/88/88 ticks, cinco evocações cada, revisão durante worker e respostas
initial/current corretas, retomada sem SQLite original e cancelamento próprios.
Pesos de tarefa/léxico constantes. RSS 204–205 MB, CPU do principal 0,36%/1,97%/3,11%
de um núcleo, p95 da iteração 1,52/1,46/1,50 ms; p99 14,6/45,0/45,2 ms. Carga concorrente
CI/testes, não agrega CPU dos filhos ou demonstra hard realtime. Primeiros loops sem
evocação interna preservados; simulador de linguagem não prova qualidade da LLM.

Qwen real: RAM inicial medida em 17,8 GB permitiu request no ensaio de 30 s
`language-probe-f74e65ff740242f9bc25918be0b9d239`; primeiro parser não concluiu.
300 ticks, 297 atendidos, 15 evocações, workers/host encerrados. Janela estendida
120 s/1.200 ticks mais 30 s de margem operacional (fake continua ≤40 s); PS registra PID.
`language-probe-cf0a98fe9a1a41808b71978bb149b8e1`: RAM subiu e primeiro pedido teve
23 recusas, uma com 22.262.435.840 B usados/total 33.461.567.488 B + reserva 4.505.915.124,75 B.
24 workers parados, 1.197 ticks atendidos/59 evocações/3 percepções, outro pedido cancelado;
zero `/api/chat` no host longo, pergunta preservada. Qualidade=false/aceitação null;
accepted é apenas continuidade/atenção. PID 23948/porta 11438 e Ollama ausentes após
fim. Log reconheceu RX 9060 XT/ROCm/gfx1200, inferência GPU não avaliada. Não alterar
limite de 75% nem processos/modelos do usuário para forçar sucesso.

Discovery final: 215 testes/240,756 s, exit 0/OK; treze específicos isolados/21,399 s OK,
CI geral exit 0. Discovery intermediário de 214 e falhas/testes/pilotos anteriores
preservados. AST/whitespace e parsePS verificados. Artefatos nos prefixes
neural-task-v2/controls,neural-language-loop-v2 e probes descritos; manifest desta
fase preserva históricos. Meta ampla ativa; módulos reais no novo fluxo, intenção
temporal completa, adaptação online de atenção, relações, novas categorias,
Rust/runtime completo e integração persistente do PC continuam pendentes.

### 11/10/2026 — Alice: admissão experimental de linguagem na GPU

Modo opt-in `language_gpu_worker.py`, runner `--device gpu`/PS `-Device gpu`.
CPU/prompt/schema/validação continuam padrão; GPU altera apenas num_gpu para -1.
Não altera pesos, checkpoints ou a autoridade de recursos da aplicação. Retomada
GPU exige factory explícita. Worker grava amostra/reserva; limpeza não retida
remove somente arquivos conhecidos, incluindo gpu-admission.json.

Reutilizou WindowsResourceProbe via modo read-only `LocalAiTests --resources`,
sem duplicar interop DXGI/PDH ou usar fallback de telemetria. Exige RAM/VRAM
globais válidas, identidade e timestamp ≤5 s; erro adia inferência. Mantém 75%
nas duas memórias e reserva fria tamanho do modelo ×1,25 +256 MiB em ambas.
Contador VRAM no sandbox retorna null; execução autorizada mede uso global.

Preregistro/resultados no laboratório. Qwen real em modo GPU, 10 s/100 ticks:
language-probe-7653fc653ffe4183a64a702126e8a529. Duas percepções, episódios 48→50,
98 ticks atendidos/cinco evocações, três workers encerrados, pergunta preservada
após duas recusas RAM; outra cancelada. RAM usada 21,516 GiB/total 31,164,
VRAM 4,157 GiB/total 15,809, reserva 4.505.915.124,75 B em cada memória. VRAM cabia,
RAM não. Zero `/api/chat`, qualidade/offload não avaliados; accepted só continuidade.
RSS principal 200.843.264 B, CPU 0,140625 s, p95 iteração 2,099 ms. PID próprio 32480,
porta 11438/Ollama ausentes ao fim; host language-host-178d04987a4444d582bb60dc478d6ce4.

Discovery 222 testes/273,080 s OK exit 0, oito específicos finais/3,546 s OK
(inclui limpeza adicionada após coleta da descoberta), CI geral final exit 0.
Build harness sem warnings, AST de 84 arquivos Python/PS/check whitespace válidos. Primeiro
comando focado teve erro de caminho dos fixtures; logs/runner correto preservados,
sem mudar expectativas. Manifest gpu-language-manifest.json inclui fontes,
checkpoints de origem, relatórios de admissão, host e verificações. Meta ampla
continua ativa; inferência GPU real e qualidade no novo fluxo ainda pendentes.

### 11/10/2026 — Alice: episódios simultâneos com correspondência neural

Novo subsistema `scene_signals/binding/memory/experiment.py`: duas regiões visuais
32×32 num canvas 32×64 e duas fontes acústicas já localizadas (estéreo 2×1024).
Compartilha encoders, detector de fronteira, relógio e banco episódico neural.
ParticipantBinding (2.177 parâmetros/8.708 B) aprende correspondência entre
vetores conceituais perceptivos; igualdade de participante é só alvo de treino.
Até quatro tracks com estado corrente e IDs internos de posse, sem exemplos.
Posição não é identidade. Ausência/conflito/dono ambíguo impede atribuição.

EpisodicMemory.observe_at permite escrita em um episódio aberto selecionado pelo
agente, preservando observe antigo e validação de boundary booleano. Pré-calcula
fronteiras/capacidade de todo o passo antes de escrever; uma atividade nova não
encerra o episódio do outro participante. Checkpoint 33 acopla base residente,
pesos de correspondência, fonte e tracks; restauração estrita/clonada e falha sem
alterar RNG. Não migra o mind paginado/temporal/linguagem completo.

Critérios definidos antes do primeiro piloto, mantidos. Piloto inicial interrompido
por janela de avaliação 1e-8 no futuro, corrigido sem alterar critérios. Três seeds
v3 (17/29/71): 1.024 pares reservados, correspondência 100%/falsos 0%; zerar rede
leva recall a 0%. Por seed: recuperação 32/32, trocas de posição 80/80, correções
isoladas 16/16 preservando initial/current e outro participante, abstenção 16/16
com identidade ausente e 16/16 em conflito modal. Próximo frame após restore igual.
Digest verifica pesos da fonte preservados, não cache; runner ~4,8 s sem startup.

Controles crossmodal nas três seeds: 64/64 lembranças usando um sentido para
aprender e o outro para consultar; pesos factuais apagados, endereços mantidos:
zero autor afirmado/64. Snapshot fonte completo preservado nesse controle.
Doze específicos finais/12,729 s OK; descoberta 233 testes/284,354 s exit 0
(dois específicos adicionados após coleta). CI final v2 exit 0; AST/whitespace
verificados. Pilotos/falhas/controles/checkpoints e manifest concurrent-scene-manifest
preservados. Ainda: mesmas quatro categorias sintéticas, duas fontes localizadas,
uma atividade por participante; eventos da mesma pessoa são ambíguos. Paginação,
núcleo temporal global/atenção/linguagem e cenas/identidades reais pendentes.
Meta ampla segue ativa, sem declarar mente/vida completa ou linguagem avaliada.

### 11/10/2026 — Alice: múltiplos eventos do mesmo participante

EventBinding em scene_binding.py (9.441 parâmetros/37.764 B float32) aprende
correspondência de participante/atividade/contexto, variando impressão. Igualdade
dos componentes é alvo apenas no treino; runtime recebe conceitos derivados das
fontes sensoriais, sem IDs prontos de eventos. Hard negatives alteram um componente;
10% dos pares mascaram uma âncora. 1.536 pares treino/1.024 reservados, 1.800 updates,
60 s e amostragem limitada. Critérios mantidos nas três seeds.

ConcurrentEventSession usa mesmo banco/encoders/relógio, até 64 tracks; diferentes
atividades da mesma pessoa não se misturam. Âncoras ausentes/fontes iguais geram
abstenção. Mudança de atividade cria evento próprio preservando anterior. Hooks de
elegibilidade/ordem/correspondência preservam ConcurrentSession antigo; checkpoint
34 tem rede/configuração próprias, 33 mantém arquitetura/comportamento anteriores.
Não migra mind temporal/paginado/linguagem completo.

Ensaios same-participant-event-pilot-seed17 e same-participant-event-v1-seed29/71:
recall/acurácia 100%/falsos 0% nos pares reservados; zerar rede derruba recall a 0%.
Por seed: 32/32 eventos, 80/80 trocas de posição, 16/16 revisões isoladas e 16/16
mudanças preservando passado, 16/16 máscaras e 16/16 conflitos com abstenção.
64/64 recuperações cruzadas e zero fatos após apagar pesos episódicos/índices
preservados. Próximo frame após restore igual; pesos da origem preservados.
Consulta sem participante em atividades/contextos iguais de pessoas diferentes
fica ambígua; pista completa recupera impressão correta. Fontes iguais da mesma
pessoa continuam indistinguíveis. Fonte localizada e categorias sintéticas.

22 focados/23,712 s e descoberta 245 testes/290,896 s OK exit 0; CI geral exit 0.
AST/whitespace de 91 arquivos Python verificados. Fontes/checkpoints/controles/logs
no manifest same-participant-event-manifest.json. Runner ~7,49/10,10/10,17 s sem
startup, RSS ~253 MB; duas seeds/testes concorrentes, sem benchmark isolado.
RAM real novamente insuficiente para Qwen + reserva fria75%: 19,572 GiB às
06:48 UTC/20,307 GiB às18:10 UTC de total31,164 GiB; VRAM disponível. Nenhuma
inferência iniciada nem reserva/teto alterados. Meta ampla permanece ativa;
paginação/atenção/núcleo global, identidades abertas, sensores e linguagem reais
seguem pendentes.
