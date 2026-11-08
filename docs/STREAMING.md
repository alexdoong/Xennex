# Streaming — desenvolvimento 0.2.x

## Prévia nativa de transmissão no Android e diagnóstico de captura (08/11/2026)

Adicionada a prévia nativa em `src/Android` (`me.xennex.live`, API 26+, compilada
com SDK 35) para compartilhar a tela do celular via `MediaProjection` + `libwebrtc`
diretamente em uma sala existente do protocolo `xennex-room-v3`. Na interface web,
`browserCaptureSupport.ts` detecta capacidades de captura sem blacklist de
User-Agent, exibe diagnóstico local sem dados privados e oferece o atalho
`xennex-live://share?room=CODIGO` quando `getDisplayMedia` não está disponível.
Abertura de link apenas preenche o formulário; a captura exige toque explícito e
autorização do Android. Escopo, limites (somente vídeo até 1280px/30FPS, até 4
espectadores/8 Mbps, sem coordenação própria e ensaio em aparelho físico pendente)
e instruções de build (`scripts/build_android.ps1`) estão em
[ANDROID_STREAMING.md](ANDROID_STREAMING.md).

## Estrutura e ordem de implementação (04/11/2026)

O objetivo integral segue em [STREAMING_PLAN.md](STREAMING_PLAN.md); a ordem
vigente é construir versões integradas do conjunto antes de polir componentes
isolados. Responsabilidades, contratos, dependências e ownership das 48 tarefas
estão em [STREAMING_ARCHITECTURE.md](STREAMING_ARCHITECTURE.md).

O consumidor JPEG agora usa `CaptureFramePipeline`: a sessão coordena fonte,
socket, fila e publicação; o adaptador cuida de decode, saída e liberação de
quadros. Apenas um backend é instanciado por captura. Canvas continua padrão;
generator/worker são opções internas experimentais, sem ativação pela UI.
Essa consolidação não elimina JPEG, não integra H.264 à sala e não comprova
correção do lag fora de foco. Ensaios manuais repetidos foram adiados conforme
a nova ordem; verificações determinísticas continuam durante a construção.

## Diagnóstico da entrada, layouts e medição local (03/11/2026)

EntryDiagnostics mantém tentativa curta, build, etapas de sinalização/registro/
ICE/canal/confirmação, contagem limitada de negociações/candidatos e códigos
STUN/TURN. Relatório copiável usa apenas campos permitidos; não inclui nomes,
código da sala, peer IDs, URLs, IPs, SDP ou credenciais. Falha deixa o painel
acessível no lobby, sem abrir Opções. APIs ausentes ou falhas síncronas de Peer,
coordenação e canal têm saída/tempo limitado; não implicam diagnóstico de NAT.
Build recebe marcador app/web+UTC via Vite para distinguir entregas da geração v3.

Palco oferece foco com miniaturas, grade e livre; trocar modo preserva elementos
de vídeo/volumes. Encaixe opcional em incrementos de 2,5% mantém borda oposta no
resize. Salvar organização guarda até32 retângulos normalizados, modo/prévias/
encaixe em xennex_stream_layout_v1; sem identidades, nomes ou sala. Aplicação pela
ordem das telas, com mínimos/limites recalculados no viewport. Storage ausente ou
corrompido não impede uso; Restaurar padrão também limpa a organização salva.

Qualidade → Medir esta sessão coleta voluntariamente RTP por60 ou900 segundos,
com parada antecipada e relatório local copiável. Limites256 conexões/512 amostras
válidas por campo, média/p50/p95/mínimo/máximo, última resolução/codec e diferenças
de descartes/freezes. Campos ausentes são null; codec é filtrado, IDs ficam só em
memória e não entram no relatório. Não salva imagens, envia relatório, infere
hardware nem mede CPU/GPU/captura bruta/latência ponta a ponta. Perfis podem mudar
durante a coleta; manter perfil fixo para comparação. Sair descarta a medição.

Após lembrete do usuário sobre lag fora de foco, separar framesReceived
(chegada antes do decoder) de framesDecoded/framesEncoded. Tiles preferem taxa de
chegada quando disponível; fallback RTP é rotulado Decodificando, não Recebendo.
Diferença de pelo menos5FPS exibe taxa de decode adicional. Relatório conta
amostras focused/unfocused/hidden/unknown; resets e intervalos acima de10s deixam
a taxa por diferenças indisponível. Nenhuma correção de throttling é presumida.
Testes headless sem flags antithrottling e tentativa minimizada ainda reportaram
documento visible; janela realmente oculta continua exigindo ensaio confirmado.

Probe nativo repetido sem builds/benchmark de browser concorrentes registrou
visible/focused e chegada≈28,1/35,3/48,9FPS nos alvos30/60/120 em800×600,
processados≈30/41/54FPS no Worker. Não atinge o alvo alto nem prova desempenho
em segundo plano. A rodada anterior sob carga concorrente chegou a≈5FPS; não
usá-la para atribuir causa exclusivamente à rede ou ao foco. Evidências em
bin/stream-plan-native-focus.log; captura → RAM/JPEG/canvas permanece gargalo
a investigar nos próximos lotes, sem alegação de encoder direto implementado.

Integração Edge real com fontes sintéticas:60s, duas entradas800×450/30, médias
28,92/29,37FPS,30 amostras por vídeo. Resultado em bin/streaming-qa/rtp-benchmark-60s.json;
não é teste de1080p120 ou internet dos amigos. Inventário do lote e pendências em
[STREAMING_PLAN.md](STREAMING_PLAN.md#execução-em-andamento--03112026).

## Plano consolidado de evolução (02/11/2026)

Backlog atual, prioridades, dependências e critérios de aceitação em
[STREAMING_PLAN.md](STREAMING_PLAN.md). Reúne estabilidade/entrada, validação no
grupo, captura e encoder nativos, compatibilidade por receptor, áudio/chamada,
interface, colaboração, entrega e pesquisas das propostas recebidas. Distingue
o que já existe, o que é experimental e o que ainda precisa de implementação.
As seções abaixo preservam o histórico técnico de cada incremento.

## Aviso visual de nova tela (02/11/2026)

Quando outro participante publica uma nova tela, destacar nome/botão Assistir
com brilho breve e degradê, além de marcador “Nova”. Contador em Pessoas e telas
continua visível no modo somente telas. Sem som, autoplay, foco ou nova permissão.
Respeitar prefers-reduced-motion. Marcador sai ao assistir/parar ou sair da sala.

Primeira presença é baseline (não avisar sobre telas anteriores à entrada).
Histórico local limitado por sessão evita repetir em heartbeat, renomeação,
reconexão/migração ou reaparecimento do mesmo ID. Ignorar câmeras/telas próprias.
Estado é do provider de streaming, compartilhado entre compacto/janela completa.

## Compatibilidade do grupo: navegador/Cloudflare primeiro (02/11/2026)

A maioria dos usuários utiliza o site; o app Windows é adicional. Escolhas de
codec usam recursos anunciados e estimativas locais do navegador, sem regras por
marca/idade de GPU. Automático preserva negociação padrão quando a informação é
ausente ou empatada; opções avançadas preferem H.264/VP8/VP9/AV1 sem excluir os
formatos restantes. Cada espectador negocia sua própria recepção, com ajuste local
em Qualidade → Compatibilidade deste dispositivo. Mudança reconecta só as suas
assinaturas; não reinicia transmissões dos outros ou a sala.

Não exigir AV1, encoders nativos ou instalação do app nos espectadores. Ausência
de getDisplayMedia desabilita compartilhar tela, não assistir via WebRTC. Isso
não garante suporte em navegadores sem WebRTC ou aceleração/fps em qualquer GPU.
MediaCapabilities fornece estimativas; benchmark e hardware de NVIDIA/Intel/AMD
antigos precisam de validação real. [Contrato e limites](STREAMING_CAPABILITIES.md).

## Captura de jogo própria: protótipo OpenGL (02/11/2026)

Fonte explícita “Jogo OpenGL · experimental”, independente do OBS: DLL x86/x64,
PBOs/fences, IPC anônimo limitado, JPEG no Worker e seleção/áudio normais do app.
No teste autorizado do osu! fullscreen, captura bruta30,0/60,0/119,7FPS, superando
o gargalo DXGI de1–2FPS. Ensaio completo sintético local644×480 recebeu cerca de
30/57/83FPS via WebRTC; não comprova1080p120 nem a entrega em redes diferentes.
Assinaturas/publicador fixados antes da captura; sem fallback automático, OBS ou
mudanças no jogo. [Estado, comandos, ciclo de vida e limites](GAME_CAPTURE.md).

## Decode, fila recente, diagnóstico RTP e teste do osu! (01/11/2026)

`CaptureFrameDecoder` usa ImageDecoder/VideoFrame quando disponível, desenhando
sem criar um ImageBitmap intermediário. Decoder e quadro têm fechamento explícito;
API ausente, JPEG não suportado ou canvas que recuse VideoFrame usa a alternativa
createImageBitmap. Cancelamento fecha o decoder e descarta resultados tardios.
Não representa encoder de hardware, zero-copy ou nova compressão de rede.

`LatestCaptureFrame` mantém um decode ativo e apenas um JPEG pendente substituível,
em vez de ignorar todos os novos quadros enquanto um decode antigo termina. O
último JPEG de uma cena parada continua sendo processado. Limite de32MiB por JPEG,
sem fila crescente; parar/fechar o socket limpa pendências. Diagnóstico local mostra
média/p95 de decode, espera local, chegada-até-desenho p95 e contagem de quadros
substituídos. “Chegada” é o evento do socket local; não inclui captura anterior nem
latência até o amigo. Desenho mede submissão, não conclusão GPU.

Comparação controlada na mesma WebView2, imagens sintéticas,26 amostras alternadas
após6 de aquecimento, JPEG85:720p bitmap2,43ms→VideoFrame1,74ms;1080p4,07→3,17ms
(p95 5,30→4,00ms). Não é ganho universal de FPS. No ensaio WGC real da janela de
teste, o caminho WebCodecs foi confirmado com decode médio2,84ms/p956ms e nenhum
quadro substituído na janela medida; carga GPU e cenas diferem de ensaios antigos.

Qualidade real por conexão acrescenta codec efetivamente usado, médias de
encode/decode por quadro, espera média de jitter buffer, perdas por intervalo,
descartes, NACK/PLI e congelamentos quando o navegador fornece os contadores.
Contadores ausentes, reiniciados ou antigos permanecem desconhecidos; codec não
comprova aceleração por hardware. Números “+” representam diferenças na janela;
não houve implementação de FEC própria, ROI, AV1 obrigatório ou troca de WebRTC.

### Resultado real no osu!: fullscreen exclusivo continua limitado

Teste autorizado em Windows build26200, sem imagens salvas: no fullscreen que o
usuário estava usando, DXGI retornava ACCESS_LOST após cada recriação. Alvos
30/60/120 tiveram respectivamente1,43/1,46/1,35FPS no socket, com12/13/12 notificações
de recuperação em≈9s por etapa. WGC da janela não produziu quadros suficientes.
Isso invalida qualquer conclusão de que o teste sintético anterior resolveu o
osu! real. Não foi confirmado o modo exclusivo por uma API do próprio jogo.

Após o usuário escolher janela/sem bordas, DXGI1080p mediu29,83/58,86/119,65FPS
nos mesmos alvos, com zero notificações de recuperação; houve251/499/1014JPEGs.
São medidas locais até o socket, não recepção no amigo. Não alteramos opções,
driver, registro do Windows, anticheat ou renderer do jogo.

Há [relato primário no OBS](https://github.com/obsproject/obs-studio/issues/14021)
com o mesmo padrão de fullscreen OpenGL/osu! em Windows recentes, inclusive no
exemplo WGC da Microsoft. É evidência de uma limitação possível da API/Windows,
não prova isolada da causa exata nesta máquina. Contorno validado nesta sessão:
**usar janela/sem bordas**. Não introduzir game hook/injeção silenciosamente.

O pacote final também passou no teste completo de recepção WebRTC, mas os alvos
não foram integralmente atingidos: na cena sintética800×600 recebeu26,9/38,9/35FPS
para30/60/120; híbrido720p/1080p24,8/20,2FPS, com a própria fonte caindo para≈31FPS
nos últimos casos. Não extrapolar o osu!119,65FPS do socket para a entrega ao amigo.
Custo de captura/canvas/encoder e visibilidade/carga ainda exigem investigação;
qualityLimitationReason=none não elimina gargalos anteriores ao encoder.


`CaptureRestartGuard` corrige o loop ilimitado em que um único quadro por sessão
zerava o orçamento de falha: três perdas próximas mostram estado fixo `unstable`;
seis em10s encerram a captura com orientação manual. Uma fonte que produz imagem
e permanece aberta por2s limpa a sequência (cena parada legítima não é falha).
Nenhuma seleção de monitor/fonte ocorre automaticamente. UI preserva avisos de
áudio, ignora texto arbitrário do worker e limpa instabilidade após recuperação
estável. Testes simulam o padrão de um quadro por abertura observado no osu!.

WebCodecs: [especificação](https://www.w3.org/TR/webcodecs/) e
[integração VideoFrame/canvas](https://developer.chrome.com/docs/web-platform/best-practices/webcodecs).

## Redimensionamento GPU e diagnóstico do pipeline (01/11/2026)

WGC e DXGI compartilham `GpuFrameEncoder`: quando necessário, redimensionam e
rotacionam a imagem na GPU **antes** do staging/map. JPEG, socket autenticado,
canvas e WebRTC continuam existentes; isto não é zero-copy nem encoder nativo.
Sem mudança de tamanho/rotação, o shader é dispensado. Não amplia fontes menores.

`GpuFrameScaler` usa compute shader D3D11 (`cs_5_0`, Vortice.D3DCompiler3.8.3),
texturas reutilizadas e amostragem de área limitada a4×4 amostras por pixel.
Saída RGBA com canais trocados mantém os bytes BGRA esperados pelo JPEG sem exigir
UAV BGRA. Recursos não suportados ativam CPU na mesma sessão, com aviso no log e
caminho indicado no diagnóstico; perda/reset de dispositivo segue a recuperação
existente. Não seleciona outra fonte. JPEGs retornados têm armazenamento próprio,
sem sobrescrever quadros retidos pelo socket. Apenas o último quadro fica pendente.

Em **Qualidade → Processamento da captura no app**, as medições locais separam:
resolução de entrada/saída, GPU/CPU/original, bytes da superfície mapeada, quadros
processados por segundo, pré-JPEG, espera/map, JPEG, média/p95 do processamento e
decodificação/desenho na WebView. Map inclui espera dos comandos GPU anteriores e
faz parte do pré-JPEG; drawImage mede envio de comandos, não conclusão na GPU.
Esses tempos não são RTT, latência ponta a ponta ou FPS RTP entregue ao amigo.

Janelas de até256 amostras/≈2s; mudanças de geometria/caminho reiniciam a janela.
Mensagens versionadas `capture-metrics` dividem o remetente serializado com JPEG,
seguem o quadro e não repetem snapshots iguais. Somente clientes autenticados
recebem as métricas; parser limita tamanho/campos. Sem pixels, caminhos ou tokens.
Amostras antigas recebem indicação explícita: cena parada pode não gerar quadros.

Validação: testes sintéticos de cores/canais, quatro rotações, dimensões ímpares,
resize repetido, ausência de ampliação, gradiente/checkerboard, JPEG imutável e
fallback real em WARP feature-level10 passaram. No ensaio alternado de24 amostras
após aquecimento, 3840×2160→1920×1080/JPEG95 com quadrantes gerados: CPU média27,04ms
(p95 30,35); GPU4,16ms (p95 5,52). Superfície mapeada33.177.600→8.294.400 bytes/quadro
(75% menor), não medição de tráfego PCIe. Conteúdo simples e uma única máquina:
não extrapolar para FPS de jogos, outras GPUs ou qualidade de rede.

WGC real em janela isolada800×600→640×480:29,49quadros/s para alvo30,
pré-JPEG2,37ms/JPEG0,59ms e p954,04ms. A WebView levou≈19,85ms para decodificar,
apontando outro gargalo possível; média de janelas distintas, sem somar como
latência ponta a ponta. DXGI exclusivo/janela/exclusivo continuou recuperando
(47 quadros vermelhos/54 azuis, três notificações), sem salvar imagens.
CI geral e regressões de captura/áudio/autenticação e salas com três publicadores
passaram. Ensaio híbrido de navegador usa outro caminho e não mede esta otimização.
Teste no osu! pessoal e entre computadores reais continua necessário.
Pacote final assinado também validado: WGC GPU 800×600→640×480 com30,58quadros/s,
pré-JPEG1,90ms/JPEG0,57ms/p953,36ms, decodeWebView15,37ms; worker single-file
recuperou37quadros vermelhos/55azuis no ensaio fullscreen pelo socket. Variações
entre rodadas reforçam que esses números são amostras, não limites garantidos.


## Tela cheia exclusiva e modo DXGI (01/11/2026)

Relato: osu! em fullscreen exclusivo congela a última imagem, inclusive na captura
de monitor. Preto no carregamento de um mapa pode ser conteúdo legítimo: não usar
detecção de imagem preta ou silêncio de uma cena parada para mudar a fonte.

No app: **Transmitir → Monitor / jogo fullscreen → DXGI → Monitor do jogo**.
Esse caminho duplica explicitamente todo o monitor escolhido. Alt+Tab pode mostrar
o desktop e outros programas dessa tela. WGC (monitor principal) continua como
opção manual; captura de janela nunca amplia seu escopo para um monitor sozinha.
O navegador continua usando getDisplayMedia, cuja implementação não controlamos.

DesktopDuplicationCapture usa Vortice.Direct3D11 3.8.3, dispositivo da GPU que
possui a saída e seleção por nome lógico do monitor. Após AccessLost/DeviceRemoved/
DeviceReset/indisponibilidade temporária, libera os recursos e recria a duplicação.
Na recuperação confere também LUID da GPU e interface do monitor: se a identidade
mudar, encerra e pede nova seleção, sem capturar outra tela silenciosamente.
Recuperação e fonte reaberta sem primeiro quadro têm orçamento de 15 s. Timeout
de AcquireNextFrame numa fonte já iniciada é silêncio normal, não falha.

O worker envia estados fixos recovering/ready pelo socket autenticado; ready
acompanha imagem válida. A UI avisa a recuperação sem apagar falhas independentes
de áudio. Envio por cliente é serializado, com apenas o último JPEG pendente;
um status em trânsito não descarta a única imagem de uma cena parada.
Tokens/origem/loopback, propriedade e cancelamento continuam obrigatórios.
O primeiro quadro DXGI tem até 20 s no frontend; o watchdog total continua finito.

Isso não injeta código no jogo nem muda osu!/driver, HDR ou configurações de
fullscreen. Não contorna conteúdo protegido/desktop seguro. O cursor desenhado
pelo jogo pertence à imagem; cursor separado de hardware do Windows ainda não é
composto pelo caminho DXGI. Esse backend ainda usa staging na RAM e JPEG antes
do canvas/WebRTC: compatibilidade de fullscreen não equivale a zero-copy ou
garantia de taxa/latência. Evolução e revisão das sugestões externas:
[STREAMING_REVIEW.md](STREAMING_REVIEW.md#avaliação-das-sugestões-de-pipeline--01112026).

Referências: [Desktop Duplication](https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api),
[suporte a fullscreen](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/desktop-duplication-api),
[invalidade por troca de modo](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutputduplication-acquirenextframe).

## Correções de entrada e captura; vídeo otimizado com áudio por processo (31/10/2026)

O coordenador recebia a oferta PeerJS antes de abrir o DataChannel, mas iniciava
nesse momento o prazo de 10 s para receber join. Uma negociação ICE lenta podia
ser encerrada antes de poder enviar a entrada. Agora há até 25 s para abrir o
canal, mais 10 s após open para confirmar join. O cliente usa o mesmo orçamento
de negociação e limita toda a entrada a 60 s; falhas explícitas aguardam 2 s antes
de repetir. Reconectar a sinalização limpa o erro transitório anterior. A interface
distingue negociação e confirmação. Mensagens/protocolo, limites e validações
continuam obrigatórios. Isso corrige uma corrida reproduzida em teste; não prova
a causa da falha histórica do amigo, cuja rede não foi reproduzida.

Na captura WGC, o último JPEG válido é guardado mesmo sem clientes e entregue
a quem conectar depois, evitando aguardar outra alteração numa janela parada.
Sem clientes, a atualização desse cache é limitada a 4 FPS para evitar codificação
em taxa máxima caso uma interface desconecte antes de encerrar o worker.
Somente um envio por socket ocorre de cada vez. CaptureFrameCadence conserva a
fase dos prazos, tolera pequeno jitter e descarta atrasos sem rajadas de compensação.
O canvas solicita captura após cada imagem decodificada com requestFrame quando
suportado; nos demais ambientes conserva captureStream(FPS). O serviço detecta
saída do worker e não anuncia ready indefinidamente; tentativas de socket consultam
esse estado. Janela inválida/minimizada é recusada e um worker anterior não é
esquecido enquanto seu encerramento não for confirmado. Token/origem/loopback
continuam obrigatórios; argumentos do processo usam ArgumentList.

**Tela, janela ou aba** passa a ser a seleção inicial. No app ela também permite
**Escolher janela / processo de áudio**: vídeo vem do seletor do navegador e somente
o áudio vem do capturador Windows. BeginBrowserCapture reserva a sessão para esse
dono, sem iniciar CaptureWorker e sem solicitar áudio duplicado ao navegador.
Vídeo/áudio permanecem independentes: falha de som avisa e mantém vídeo; parar/cancelar
libera ambos. O app conserva uma única sessão de áudio por processo/vídeo nativo;
o aviso de ocupação aparece junto às fontes e permite escolher captura do navegador
com áudio próprio para outra transmissão. Sites comuns não recebem essa ponte.

Essa combinação evita converter vídeo WGC para JPEG e decodificá-lo antes de
recodificar para WebRTC. As opções antigas de janela/monitor nativo continuam
disponíveis, com seus limites de processamento. Não há geração artificial de
quadros, ampliação de fontes menores nem garantia de 60/120 FPS em qualquer fonte,
hardware ou rede. As medidas RTP continuam sendo as de cada conexão.

Pacote final validado com fonte sintética e áudio real da instância isolada:
59,1 FPS recebidos em 720p/60 e 54,7 FPS decodificados em 1080p/60 em rodadas
separadas. O ensaio completo da própria janela sob carga teve valores menores,
inclusive na fonte; não é comparação controlada nem prova de taxa sustentada.
120 FPS e captura real de jogos entre redes continuam sem validação de desempenho.

Configuração local wrangler.jsonc sincroniza observability.logs (enabled,
invocation_logs, persist), conforme o painel enviado pelo usuário. Sem deploy,
isso não altera o Worker remoto. TURN continua desligado, sem autenticação ou
instalação da integração Cloudflare nesta etapa.

A versão do projeto é 0.2.4 (desenvolvimento). O pacote portátil é gerado por
`scripts/package_release.ps1`; a página pública precisa de upload separado.
O empacotamento não publica no Cloudflare.

A [revisão geral de 06/10/2026](STREAMING_REVIEW.md) registra o estado testado,
problemas confirmados de áudio, limites de qualidade/carga e prioridades para
evoluir o serviço antes de adicionar novas funções.

## Correções de inicialização e áudio (06/10/2026)

App, compacto e navegador mostram **Preparando transmissão**, a etapa atual e
tempo decorrido. Etapas: escolha/permissão da fonte, início do vídeo, primeira
imagem, áudio e publicação. Após dez segundos aparece orientação; **Cancelar
captura** fica disponível até iniciar a limpeza. Não há percentual fictício.
O seletor do navegador pode precisar ser fechado manualmente: cancelar libera
a tentativa do app e descarta mídia recebida depois, sem publicar essa mídia.

Chamadas e etapas têm limites de tempo. O seletor tem até dois minutos e a
câmera até trinta segundos; socket local até quinze segundos e primeiro frame
até oito. Há watchdog de inicialização de 45 s para captura nativa/câmera e
150 s para navegador. A limpeza é aguardada separadamente. Uma janela visível
que não entrega o primeiro frame gera mensagem em vez de loading indefinido.

`captureStartup.ts` centraliza espera cancelável, timeout e limpeza de respostas
tardias. `CaptureProgress.tsx` apresenta progresso; `useRoom` compartilha estado
entre compacto e janela completa. O serviço mantém o dono da sessão até o
início pendente e a limpeza terminarem, impedindo que um worker atrasado pare
uma captura nova.

A ponte usa `BeginNativeCapture`, `BeginCaptureAudio`, `GetCaptureState` e
`StopCaptureAudio`, todos associados ao dono da sessão. O retorno de Begin
significa **aceito**, não pronto. Início/parada pesados rodam em tarefas de
background; a UI consulta o estado. Métodos síncronos antigos permanecem por
compatibilidade, mas não são usados pelo novo fluxo de captura.

O áudio estéreo float32 preserva a amplitude da fonte, sem ganho fixo 1,5×.
Falha na preparação gera aviso e permite vídeo sem som. Fechamento/erro do
socket ou encerramento do worker após início para a faixa de áudio, libera os
recursos e avisa na transmissão correspondente. Vídeo continua. Para recuperar
o som, pare e reinicie essa transmissão; reconexão automática de áudio ainda não
foi implementada. Silêncio normal não é considerado falha.

Diagnóstico separa bitrates de áudio/vídeo RTP e informa quando o encoder não
aplicou o ajuste solicitado. Configuração ICE é validada antes de anunciar
TURN; JSON/URLs inválidos voltam ao STUN padrão com aviso no log. Permanecem
os limites da arquitetura: uma captura nativa por instância, upload dividido
por conexão, dependência de sinalização e ausência de TURN por padrão.

Validação desta implementação: CI completo com StreamingTests, builds app/web,
lint sem erros (12 avisos preexistentes), regressões de captura e integração
Edge/PeerJS/WebRTC passaram. Seletor pendente mostrou loading, cancelou e
descartou mídia tardia. Teste local entregou 1920×1080 a 60 FPS. No pacote novo,
WebView2 capturou a própria janela 800×600 na primeira tentativa em três ciclos,
com primeiro frame em 411/314/325 ms. Áudio de processo da instância isolada
iniciou e permaneceu ativo durante silêncio. Isso não substitui escuta de áudio
real ou testes de carga entre redes diferentes.

## Arquitetura

### TURN opcional e isolado — base implementada (31/10/2026; ativação externa pendente)

O usuário quer preservar o funcionamento atual e disponibilizar retransmissão
somente quando necessária e para quem a solicitar. Broker Cloudflare e opção
por participante foram implementados e testados localmente; o serviço não foi ativado.
Contrato, configuração e limites em [STREAMING_TURN.md](STREAMING_TURN.md).
Franquia não equivale a bloqueio de
cobrança: confirmar controle de gastos antes de habilitar qualquer serviço.

- Padrão continua direto, sem solicitar credenciais TURN ao Worker. Não injetar
  TURN globalmente pelo VITE_ICE_SERVERS para todos os participantes nessa proposta.
- Primeiro recorte: após falha de entrada, oferecer **Tentar conexão alternativa**.
  Obter credenciais curtas e repetir a entrada somente daquele participante, com
  STUN e TURN disponíveis, sem forçar retransmissão para todos. Registrar o caminho
  efetivamente escolhido. Falha/indisponibilidade do Worker não altera a sala.
- O PeerJS instalado recebe RTCConfiguration no PeerJSOption da instância;
  PeerConnectOption/CallOption não expõem configuração ICE por chamada. Não
  presumir que basta acrescentar uma opção em connect/call. Isolar configuração
  por participante e validar o comportamento antes de tentar recuperação por mídia.
- Esse recorte atende quem ainda não conseguiu entrar, sem mídia local em andamento.
  Não reutilizar start/leave como recuperação de alguém já transmitindo: isso
  encerra as fontes daquele participante. Recuperação de uma mídia já aberta exige
  negociação/recriação limitada à conexão afetada e testes específicos do PeerJS.
- Uma alternativa pode precisar reconectar o participante ou vídeo afetado; não
  prometer troca sem interrupção. Nunca recriar a sala, forçar eleição de coordenador
  ou fechar conexões saudáveis para ativar TURN. Sem aumento automático de orçamento
  ou ativação paga em resposta a erro.
- Critérios: modo desativado preserva caminho existente e não consulta o Worker;
  ativação por pessoa não muda ICE das outras; credenciais vencidas/indisponibilidade
  falham com mensagem; áudios, volumes e conexões dos demais continuam; desligar
  a opção permite nova tentativa direta. Automação futura requer habilitação explícita.

O acesso exige código privado em memória; não existe solicitação automática no
modo normal. Validade e renovação explícita aparecem para quem ativou a alternativa.
O Worker padrão desligado não emite credenciais. Não houve deploy nem uso de relay
real; os testes exercitaram o broker simulado e P2P real sem interromper os demais.
WebRTC foi mantido: trocar transporte não altera permissões de captura de processos
do Windows. Captura nativa por processo continua disponível no app, sem expor a ponte
de captura a sites externos.

### Falha persistente ao entrar — diagnóstico adicional (31/10/2026)

Usuário relata que um amigo sempre apresentou falha de entrada, com exemplo de
25/10/2026; não há logs dessa instalação disponíveis para confirmar a causa.
O texto “A conexão com a sala não completou” vem do prazo de 35 s quando houve
identidade na sinalização, mas o canal de dados da sala ainda não abriu. Isso
orienta a investigação, sem provar bloqueio específico de rede ou navegador.
O canal de presença também é WebRTC e pode precisar de TURN, antes de qualquer vídeo.

`connectionDiagnostics.ts` observa o transporte do canal de entrada: estados ICE,
conexão/coleta, quantidade de rotas observadas por categoria e códigos de erro
STUN/TURN. Não registra SDP, endereços, URLs de servidores ou credenciais.
Respostas de conexões antigas são ignoradas e o fechamento remove observadores.
Um candidato coletado não prova conectividade; um erro de consulta isolado não
significa que todos os servidores falharam. Configuração TURN não prova serviço ativo.
**Opções da conexão → Copiar diagnóstico** inclui fase, protocolo e presença de
TURN, inclusive após erro. O texto de ajuda explica que uma rede restrita pode
impedir tanto a entrada quanto a mídia. Isso é instrumentação, não correção comprovada
do problema desse amigo. Não foi adicionado serviço TURN nem alterado o timeout.

Quando possível, comparar o mesmo PC/navegador na rede habitual e em hotspot móvel;
sucesso no hotspot aponta para diferença de rota/rede. Se falhar nas duas, avaliar
perfil/extensões, VPN/proxy e política de WebRTC, sem presumir que a marca do browser
determine o resultado. Não orientar desativação geral de firewall/antivírus.
Referências: [TURN no WebRTC](https://webrtc.org/getting-started/turn-server) e
[políticas WebRTC do Brave](https://support.brave.app/hc/en-us/articles/360017989132-How-do-I-change-my-Privacy-Settings).

Validação: testes determinísticos cobrem estados, deduplicação, remoção de observers,
conexão antiga e ausência de IP/SDP/credenciais no log. Integração Edge sintética
verifica estados ICE reais e cópia do diagnóstico após falha; CI, lint e builds
app/web passaram. Publicação do bundle continua pendente; não foi acessada a sala
do usuário ou reproduzida a rede do amigo.

### Apresentação e medidas por transmissão (31/10/2026)

A sala prioriza as telas. **Transmitir** no topo abre `StreamCapturePanel`, um
diálogo com escolhas de fonte, áudio, resolução e atalhos de 30/60/120 FPS ou
automático. Valores personalizados continuam disponíveis. Prioridade, entrega e
upload ficam em ajustes avançados. As escolhas permanecem ao fechar/reabrir o
painel; publicar fecha o painel e mantém o vídeo montado. Fontes nativas e áudio
por processo preservam os contratos existentes. O seletor de telas do navegador
continua sendo confirmado pelo usuário, sem captura de prévias silenciosa.

**Pessoas e telas** abre/fecha a lista com ações textuais Assistir/Parar, inclusive
em **Somente telas**. **Qualidade** mostra o diagnóstico sem sair desse modo.
O progresso de captura aparece no painel ou na sala se o painel estiver fechado.
Fechar o painel não encerra captura/transmissão; parar e cancelar são ações próprias.

O palco usa a altura disponível da janela, recalculada ao alternar controles e
redimensionar. Grade e organização livre preservam os elementos de vídeo e seus
volumes. Duplo clique no vídeo alterna destaque; cliques nos controles não fazem
isso. No modo livre, título move; oito bordas/cantos redimensionam com cursor e
setas. A borda oposta fica ancorada e a geometria respeita mínimos e limites do
palco. O tamanho inicial considera proporção e largura, evitando preencher toda
a altura com dois vídeos estreitos. Não há persistência de layout entre sessões.

`RoomDiagnostics` consulta WebRTC a cada dois segundos e compartilha as medidas
com os tiles. `streamStats.ts` calcula diferenças de framesDecoded/framesEncoded
e bytes quando presentes, sem converter contadores ausentes em zero. Reinício de
contador e intervalos longos iniciam outra linha de base. O tile remoto mostra
**Recebendo** quando há FPS RTP; na ausência deles, mede **Exibindo** com
requestVideoFrameCallback (ou contador de reprodução quando utilizável). A prévia
local é identificada separadamente. FPS indisponível não é 0 FPS; ausência medida
de novos quadros pode ser zero, inclusive em uma cena estática. Medidas de exibição
não provam a taxa recebida nem ultrapassam necessariamente a frequência do monitor.

Alvo e formato configurado da captura aparecem nas informações da prévia e no
diagnóstico de envio. Restrições silenciosamente reduzidas pelo browser geram
aviso quando identificáveis. Automático não solicita mais 120 FPS na segunda
aplicação de constraints do browser; o teto do encoder/nativo permanece 120.
O diagnóstico informa o teto por cópia, o número total de cópias e limitações do
encoder/rede. Não houve mudança para SFU nem promessa de FPS/resolução garantidos.
Exemplo: upload total de 12 Mbps com três cópias deixa até 3,4 Mbps por cópia,
considerando a margem de 15%; várias fontes também entram nessa divisão.

Validação: npm test (incluindo resize ancorado e amostras RTP ausentes/zeradas/
reiniciadas), lint sem erros (12 avisos anteriores), builds app/web e CI completo.
Edge/PeerJS/WebRTC com três publicadores verificou foco por duplo clique, cantos,
teclado, movimento até a parte inferior, FPS recebidos, painéis no modo somente
telas, diálogo móvel, volumes, áudio simultâneo e migração normal/abrupta. Ensaio
WebRTC local 1080p/60 mediu 1920 × 1080 e 57 FPS recebidos em uma amostra. Não é
avaliação sustentada entre redes ou hardware dos amigos. Build isolado:
`bin/StreamingPreview/net8.0-windows/Xennex.exe`. Bundle público gerado em
`cloudflare_pages/dist`; publicação externa continua separada.

`frontend/src/features/stream/StreamWorkspace.tsx` é a interface compartilhada
pelo app, janela separada e navegador. `RoomClient.ts` mantém presença, mensagens,
assinaturas de vídeo, reconexão e encerramento. `protocol.ts` valida mensagens;
`quality.ts` calcula proporção e orçamento de upload; `capture.ts` gerencia mídia
e limpeza; `captureSocket.ts` aguarda o processo auxiliar com tentativas limitadas;
`StreamStage.tsx` e `stageLayout.ts` organizam as telas; `StreamVideo.tsx` apresenta
vídeo e controles; `RoomDiagnostics.tsx`
mostra estatísticas reais de conexão. A aba permanece montada durante a navegação.

Cada participante usa uma identidade de mídia estável. `RoomCoordinator.ts` recebe
presença e autoriza assinaturas por uma segunda identidade PeerJS, ligada ao código
da sala. O coordenador não retransmite vídeos. Quando ele sai ou cai, os demais
competem pelo mesmo identificador de coordenação com atrasos ordenados; PeerServer
concede esse identificador a apenas um deles. O vencedor reconstrói a presença e
assinaturas. As conexões de mídia existentes entre sobreviventes permanecem abertas.
A eleição pode levar alguns segundos e depende da disponibilidade da sinalização.
Não existe mais botão de encerrar a sala para todos: cada pessoa sai individualmente.
A saída da última pessoa libera o código. Não há sala persistente vazia no servidor.

Limites de desenvolvimento: 32 participantes, seis fontes simultâneas por pessoa,
e até 32 fontes assistidas por participante. Toda pessoa pode transmitir enquanto
assiste. O catálogo identifica cada tela/câmera separadamente. Não há assinatura
automática: cada espectador escolhe fontes e ativa áudio/volume independentemente.
Destacar um vídeo mantém os outros áudios selecionados em reprodução.
“Somente telas” reduz os painéis e mantém ações no topo para abri-los. “Organizar livremente”
permite mover pela alça superior e redimensionar pelas bordas/cantos (também com as setas
do teclado). A disposição acompanha o tamanho da área e pode ser reorganizada;
não é salva entre sessões. Alternar layouts preserva elementos de vídeo e volumes.
As próprias prévias podem ser ocultadas sem parar a transmissão.

App e navegador permitem várias telas e câmera (inclusive duas telas mais câmera).
Cada nova tela abre o seletor do navegador; câmera pode incluir microfone. No app,
existe também captura nativa com áudio de processo. Janela de vídeo e fonte de
áudio têm seletores independentes; áudio pode vir de outro processo ou seguir a
janela do vídeo. A captura de áudio inclui a árvore do processo, não isola abas
ou janelas que compartilham o mesmo processo. A enumeração preserva cada HWND e
inclui processos de áudio sem janela. Esse pipeline nativo permanece
limitado a uma fonte por instância: use o seletor para as telas adicionais. As opções
de áudio das telas do navegador dependem da fonte e das permissões do browser.

Na captura via seletor do navegador, o Xennex solicita `restrictOwnAudio` quando
o navegador declara suporte e prefere `windowAudio: "window"`. Isso pode retirar
o áudio reproduzido pela própria aba do Xennex e oferecer somente o som da janela
selecionada, mas não exclui uma chamada em outro aplicativo ou aba de uma captura
de áudio do sistema inteiro. O seletor continua sob controle do usuário e o
navegador pode ignorar as preferências. A interface avisa sobre esse limite.

A resolução é selecionável de 720p a 4K ou Original, por fonte. FPS aceita valores
inteiros de 0 a 120: 0 é automático, 1 a 120 são limites solicitados. No pipeline
nativo e na codificação o modo automático usa teto de 120; no seletor não fixa uma
taxa de captura. Um pedido de 120 FPS não garante 120 quadros reais. Fonte, câmera,
GPU, CPU e conexão podem entregar menos. O capturador nativo respeita também 1–14 FPS.

Os códigos são convites, não autenticação de usuários. O limite de participantes
não é garantia de desempenho: a mídia ainda é P2P, com uma cópia por espectador e
fonte. O orçamento informado é compartilhado entre todas as conexões de envio.
Para um grupo grande assistindo a muitas fontes em alta qualidade, a evolução de
infraestrutura é um SFU; ampliar o limite da sala não elimina esse custo de upload.

A captura nativa passa por Windows Graphics Capture, leitura de textura, JPEG,
WebSocket local, canvas e WebRTC. Preserva proporção, evita ampliar fontes menores
e ajusta textura ao redimensionar a janela. Ainda há custo de CPU/cópias: não é
um encoder de hardware com caminho sem cópias. A taxa de amostragem do áudio vem
do serviço nativo; o WebAudio faz a conversão, sem ganho artificial.
`CaptureSessionService` impede duas janelas de controlar a mesma captura.

O padrão “Preservar resolução escolhida” usa `maintain-resolution` e escala de
codificação 1; o modo adaptativo permite priorizar fluidez. FPS permanece um alvo/
teto, e não garantia. As restrições do navegador pedem tamanho ideal até o limite
da fonte, sem ampliar imagens menores. Ajustes RTP são serializados por conexão
para evitar transações concorrentes. O orçamento de upload (1–1000 Mbps) continua
dividido entre cópias com 15% de margem; não é uma reserva garantida de banda.
Os tiles distinguem medidas recebidas por RTP, exibição e prévia local. “Qualidade real por conexão”
mostra envio/recebimento, dimensões, FPS, bitrate, alvo e limitações reportadas de
rede/CPU, além de latência e relay. Uma cena parada ou uma aba em segundo plano
pode ter menos quadros. Veja a [API setParameters](https://developer.mozilla.org/en-US/docs/Web/API/RTCRtpSender/setParameters).

A captura nativa tenta conectar ao worker por até 15 segundos, tolerando o intervalo
entre iniciar o processo e abrir seu WebSocket. Cancelar mantém a inicialização
bloqueada até liberar os recursos. Encerramento antes da publicação não deixa uma
transmissão fantasma. Uma janela indisponível não é substituída pelo monitor inteiro.

## Testar localmente

Na raiz, execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_dev.ps1 -StreamingPreview
```

Isso compila e abre `bin/StreamingPreview/net8.0-windows/Xennex.exe`, usando dados
locais dessa saída. Feche sua instância anterior antes de abrir a nova, pois há
controle de instância única. Para somente compilar, acrescente `-BuildOnly`.
Este build requer o ambiente de desenvolvimento; para distribuir aos amigos,
use exclusivamente o empacotador obrigatório descrito em AGENTS.md.

Para o browser, em `frontend`, execute `npm run build:web`. Sirva
`cloudflare_pages/dist` por HTTP em localhost (ex.: Python http.server), ou HTTPS
no Cloudflare. Compartilhamento de tela requer contexto seguro e clique do usuário.

## Validação automatizada e manual

- `npm test` em `frontend`: contratos, proporção, bitrate, presença, identidade,
  múltiplas fontes, escolha independente, saída, migração normal/abrupta, entrada
  após migração, 12 participantes simulados, admissão de 32 e rejeição do 33º;
  retry/cancelamento/timeout do worker, HWND/PID independentes, limites do layout
  e ajustes de qualidade serializados.
- `npm run build` e `npm run build:web`: TypeScript estrito e bundles separados.
- `frontend/tests/browser-streaming.mjs`: Edge headless com Playwright; exige
  módulo Playwright disponível por `XENNEX_PLAYWRIGHT_PATH` e site servido em
  `http://127.0.0.1:5179` (ou `XENNEX_TEST_URL`). Usa sinalização PeerJS real,
  sessões WebRTC com três transmissores, duas telas mais câmera, áudio simultâneo,
  saída/migração, entrada tardia, fechamento abrupto do coordenador, arraste,
  redimensionamento e preservação de áudio/volume ao alternar layouts. Usa fontes
  sintéticas e não captura tela, microfone ou câmera pessoais.
- `frontend/tests/browser-stream-quality.mjs`: WebRTC local real no Edge, vídeo
  sintético 1920×1080 com alvo de 60 FPS; verifica dimensões recebidas e parâmetros
  de preservação. Não depende de PeerJS nem captura conteúdo pessoal.
- `scripts/tests/test_stream_native.ps1`: cria uma cópia isolada do pacote e usa
  WebView2 real para capturar somente a própria janela de teste em três ciclos;
  precisa do app pessoal fechado e Playwright em `XENNEX_PLAYWRIGHT_PATH`.
- `scripts/tests/test_release.ps1`: validações isoladas de empacotamento/atualização.

Antes de considerar estável, testar manualmente: app ↔ navegador em PCs/redes
diferentes; áudio de processo e sistema; janela redimensionada/minimizada; monitor
ultrawide; troca de abas; fechar popout; cancelar seletor; suspensão/reconexão;
mais espectadores e redes que exigem TURN. Os testes sintéticos não validam esses
casos nem comprovam qualidade de áudio capturado no Windows.

## Publicação web e compatibilidade

O protocolo novo é `xennex-room-v3`, incompatível com a página antiga. Atualize
app e site juntos. Veja [Cloudflare](../cloudflare_pages/README.md). Nenhum deploy
é feito pelo build. O app verifica `xennex-stream.json` antes de copiar convite.
A sinalização padrão depende do serviço público PeerJS; TURN não vem configurado.
A configuração opcional fica em `frontend/.env.example` e deve ser igual nos dois
builds. Credenciais incluídas no frontend são públicas; não use segredos de conta.


Referências de API: [ciclo de vida PeerJS](https://peerjs.com/client/api/peer) e
[restrições de FPS](https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/frameRate).

## Entrada em salas de versões anteriores

Salas abertas pelo app/site antigo não aparecem no protocolo atual, mesmo que o
código seja igual. Antes de atualizar o Cloudflare, teste somente entre instâncias
do app atualizado ou a página local gerada. A primeira pessoa usa Criar sala;
as demais usam Entrar. A página pública precisa de um novo deploy do dist.
O diagnóstico agora distingue sala não encontrada, falha na sinalização e timeout
de conexão. Uma negociação pendente tem 15 segundos antes de ser refeita, evitando
o reinício prematuro a cada cinco segundos; há teste de uma conexão de 6,5 segundos.

### Verificação no app completo (12/09/2026)

Criação e retorno à sala passaram em três ciclos no WebView2 real, com um
participante no Edge e migração entre eles. O teste reproduzível está em
`frontend/tests/webview-room-entry.cjs`: use uma instância de teste do app com
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9226`, site local
na porta 5179 e Playwright em `XENNEX_PLAYWRIGHT_PATH`. Ele encerra essa instância
após os testes; não execute durante uma sessão pessoal. A porta de diagnóstico
não é habilitada nos builds normais.

Também foram validadas conexão de 6,5 segundos e recuperação após falha temporária
no registro do coordenador. Opções da conexão → Diagnóstico da conexão mostra as
últimas etapas em caso de falha. A falha relatada não foi reproduzida no app antigo
nesta rodada, portanto não se atribui com certeza a ocorrência a uma causa única.
### Validação da visualização e qualidade (21/09/2026)

Passaram os testes unitários de streaming, compilação .NET e integração WebRTC
com três transmissores e migração. O teste de qualidade entregou 1920×1080 a 59 FPS
com alvo de 60 FPS, sem limitação reportada, em conexão local. Isso não comprova
1080p60 entre redes diferentes. A separação HWND/PID foi validada com captura
sintética; ainda é necessário ouvir dois aplicativos reais para avaliar isolamento
e fidelidade do loopback no computador do usuário.

O pacote self-contained também passou em três ciclos reais de início/parada de
captura nativa no WebView2, sem repetir o comando: primeiro frame em 937, 246 e
250 ms. O teste usou apenas a janela da instância limpa (800×600). Executável
principal e CaptureWorker da raiz foram atualizados pelo empacotador oficial.
