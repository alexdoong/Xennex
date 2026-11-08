# Validação local

## Transmissão no Android e diagnóstico de captura web (08/11/2026)

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_android.ps1`
executa `:app:assembleDebug`, `:app:testDebugUnitTest` e `:app:lintDebug` usando
as ferramentas isoladas em `bin/AndroidTools`. Os testes JUnit cobrem
`RoomAddressTest`, `CaptureSizeTest` e `RoomRosterTest` (normalização, rejeição
de entradas inválidas/injetadas, dimensões pares sem upscale e contrato de
presença v3). Na camada web, `frontend/tests/browser-capture-support.test.mjs`
(incluído em `npm test`) valida detecção de capacidades sem bloqueio por
User-Agent, erros de permissão e ausência de dados privados no relatório;
`frontend/tests/browser-capabilities-ui.mjs` verifica o link
`xennex-live://share?room=CODIGO`, o diagnóstico na modal de transmissão e a
colaboração em tempo real (chat, notas com preservação de rascunho em conflito e
tarefas). Ensaio em aparelho Android físico permanece pendente conforme
[ANDROID_STREAMING.md](ANDROID_STREAMING.md).

## Alice e palavras isoladas (08/11/2026)

`test_alice_native_pronunciation.py` cobre alinhamento, ambiguidade, limites,
origem, duplicata e arquivo portátil. Os testes de stream e gateway cobrem os
recibos de ensino/consulta e restauração de páginas. O painel headless exercita
os dois botões de prática. O ensaio separado em `bin/AliceMemory/spoken-patterns-20261108`
usou o worker real e duas vozes locais, com palavras reservadas e controles.
[Protocolo e resultados](ALICE_EPISODIC_CONTEXT.md)

## Alice e associação de um som a uma imagem nomeada (08/11/2026)

`test_alice_native_audio_naming.py` cobre evocação, bancos separados, conflito,
ablação do leitor visual, atraso e retomada. Os testes de stream e gateway
cobrem recibos e publicação de PNG+WAV em um único frame. O painel headless
cobre seleção conjunta, ensino focado e apresentação da hipótese. No ensaio
com o encoder real, os sinais foram WAVs sintetizados e os nomes ensinados
externamente à imagem. [Resultados](ALICE_EPISODIC_CONTEXT.md)

## Alice e influência do parser no ensino (08/11/2026)

`test_alice_context_report.py` cobre o valor permitido na gramática, frases
qualificadas, compatibilidade de proveniência e tentativa de usar a regra
antiga em uma escrita nova. O ensaio opcional com modelo local instalado usa
`scripts/tests/probe_alice_feedback.ps1 -Probe dialogue_learning_probe`. Ele
mede escrita e releitura em eventos simulados e, separadamente, a fala
gerada sobre evidência congelada. [Resultados](ALICE_DIALOGUE_COMPARISON.md)

## Alice e recortes visuais (08/11/2026)

Rode os módulos abaixo no Python isolado de percepção, a partir da raiz do
repositório. No PowerShell, use `$env:PYTHONPATH = 'scripts/tests'` para carregar
as fixtures partilhadas.

```powershell
& $pythonAlice -m unittest scripts.tests.test_alice_native_regions scripts.tests.test_alice_native_stream
```

Os contratos cobrem caixa real em pixels, origem, recuperação multimodal sem
texto, abstenção entre episódios, atenção, controles com recorte trocado,
worker, descarte e restauração de páginas. O modo automático testa caixa de
fundo ignorada, status no recibo, falha do detector com a cena preservada,
restauração e configuração no painel. O ensaio separado executa a DLL e os
pesos fixos do Mirage com o encoder instalado em CPU, usando PNGs desenhados,
composições de fotografias e vetores de áudio sintéticos. Resultados em
[ALICE_EPISODIC_CONTEXT.md](ALICE_EPISODIC_CONTEXT.md).

## Contrato de saída dos quadros (04/11/2026)

`frontend/tests/capture-pipeline.test.mjs` participa de `npm test`. Confere
ownership/liberação, fallback de decoder preservando a trilha publicada,
cancelamento durante decode, transferência do buffer ao worker, limite de escrita
simultânea, rejeição de métricas inválidas e erro preservado após falha do worker.
Usa doubles e não captura tela, abre jogo ou mede desempenho. Não comprova
transferência de WritableStream no WebView2 nem desempenho em segundo plano;
essas integrações reais permanecem pendentes para a etapa de uso.

## Encoder GPU e transporte nativo isolados (03/11/2026)

`NativeEncoderTests --contract-tests` participa de test_ci.ps1 sem COM/GPU/rede:
limites de perfis, ABI COM/RTC, SPS/AnnexB e rejeição de entrada inválida.
Ensaios GPU em `test_native_encoder.ps1` são opt-in, com timeout externo;
relatórios sintéticos em bin/native-encoder-*.json. Nenhum captura imagens pessoais.
1080p120 passou no estágio de encode e decoder independente; não equivale a
120FPS de captura/transmissão/renderização. Transporte browser experimental em
frontend/tests/native-encoder-streaming.mjs, fora do gate padrão e do app atual.
Consultar NATIVE_ENCODER.md para critérios e limitações.

Ensaio RTC válido720p30 recebeu/decodificou120 quadros e conferiu quadrantes RGB;
minimizado, com emulação de foco desligada, reportou visible/hasFocus=false e5
callbacks de exibição. Não simular hidden sobrescrevendo a API.1080p120 exige
opt-in adicional de estresse porque ultrapassa o nível H.264 anunciado; relatório
marca essa diferença e não é gate de qualidade negociada. Agora há modo adicional
de consulta específica e nível maior negociado:1080p120,240 quadros, fase hidden
real e retomada≈18ms, com timeline. PLI recuperou primeiro IDR omitido; teste X509
negativo rejeitou fingerprint inválido sem mídia. Perfil próprio/noDefaults e
HTML inicial evitam override de visibilidade; não navegar para HTTP e presumir
hidden nesse harness. Nenhum SDP/candidato
é persistido; logs guardam apenas contagens/estados e categorias TLS filtradas.

## Entrada, layout persistente e benchmark RTP (03/11/2026)

streaming.test.mjs cobre relatório sem dados privados, snapshots imutáveis,
histórico limitado, timeout separado de sinalização/canal/confirmação, falha
síncrona de inicialização/registro/canal e limpeza ao sair. Layouts rejeitam
JSON/versões inválidas, limitam slots, removem campos extras e mantêm geometria
válida; encaixe mantém a borda oposta no resize. Benchmark testa duração/parada,
limites256/512, distribuições, contadores ausentes como null e ausência de IDs.

browser-streaming.mjs usa sala própria PeerJS e mídias sintéticas: cópia segura
após falha,1 minuto real de duas conexões RTP, persistência/reload/móvel/reset e
foco com miniaturas sem recriar vídeos ou interromper áudio. Relatório agregado
e imagens de QA ficam em bin/streaming-qa. Não usa TURN real ou captura pessoal.

Frames recebidos e decodificados têm testes independentes (60FPS chegando/5FPS
decodificando, reset e intervalo suspenso). Benchmark registra foco/ocultação por
amostra. A integração remove as flags Playwright que desabilitam throttling; ainda
é necessário conferir a visibilidade real. Nesta rodada, headless e tentativa
minimizada reportaram visible, portanto não validaram documento oculto de verdade.
stream-capture-native.mjs registra activityBefore/activityAfter e processedFps do
Worker para distinguir produção, envio, chegada e decode. Não usar seu gate
funcional (>0FPS) como evidência de cumprimento do alvo30/60/120.

## Aviso visual de tela nova (02/11/2026)

`npm test` inclui stream-announcements.test.mjs: primeira presença/baseline,
novos IDs, heartbeat/renomeação, assistir/parar, reaparecimento em migração,
exclusão de próprio compartilhamento/câmera e reset de sessão. A integração
browser-capabilities-ui.mjs também confere botão/nome/contador com painel oculto,
sem assistir automaticamente; animação finita, reduced-motion e selo removido
ao assistir. Usa apenas sala e imagens sintéticas, no localhost ou URL de teste.

## Codecs e compatibilidade web (02/11/2026)

`npm test` inclui stream-capabilities.test.mjs: APIs ausentes/negadas/lentas,
cache limitado, perfis saneados, encode/decode independentes e reordenação SDP sem
remover payloads, perfis, RTX/FEC, áudio ou ICE. streaming.test.mjs cobre mudança
de recepção isolada e consulta tardia que não responde após cancelamento.

`node tests/browser-stream-capabilities.mjs`: WebRTC real local, vídeo sintético,
preferência AV1 com receptor limitado a VP8/H.264; pares modernos AV1 e H.264.
`node tests/browser-capabilities-ui.mjs`: site servido em localhost5187 (ou
XENNEX_TEST_URL), sala PeerJS própria, transmissor avançado e espectador móvel
limitado a VP8, sem APIs de detecção/captura de tela. Confere assistir, preferência
local/reconexão, transmissor preservado e layout390px. Não usa dados/tela/câmera
pessoais. Simula limitações de capacidades; não é teste de GPU antiga física.

## Protótipo de captura de jogo OpenGL (02/11/2026)

Teste opt-in `CaptureWorkerTests --game-hook --native-directory <pasta>` cria só
processos OpenGL próprios ocultos x86/x64; confere imagem, canais/origem, estado
GL, cadência e ciclos com redimensionamento. Exige build C separado; não faz parte
do CI sem GPU, não injeta em jogos por padrão nem captura desktop. Ver comandos e
probe real explicitamente autorizado em [GAME_CAPTURE.md](GAME_CAPTURE.md).

## Fullscreen e DXGI (01/11/2026)

CaptureWorkerTests integra o CI sem capturar telas: simula perda/reabertura de
saída, preservação de nome/GPU, prazo de recuperação, ausência de primeiro frame,
erro fatal, descarte de recursos e concorrência entre status e JPEG. StreamingTests
cobre propriedade do backend e seleção explícita. npm test cobre despacho DXGI,
ausência de fallback de janela para monitor e preservação do aviso de áudio.
monitor-capture-ui.mjs verifica escolha de monitor principal/secundário, método,
persistência da seleção e viewport móvel com API simulada, no servidor local.

Teste interativo opcional, somente com usuário disponível/autorizações para tomar
o foco e capturar o monitor durante a cena sintética:

```powershell
dotnet run --project scripts/tests/CaptureWorkerTests/CaptureWorkerTests.csproj -c Release -- --fullscreen
```

Gera janela Direct3D11 vermelha/azul, confirma SetFullscreenState, alterna
exclusivo/janela/exclusivo em cerca de 6 s e verifica JPEGs gerados. Não salva
quadros nem modifica o osu!. Fora da fase fullscreen, não inspeciona os pixels.
Sempre libera a saída de fullscreen e recursos no encerramento normal. Ao lançar
via script, usar processo próprio e watchdog finito. Resultado inicial autorizado:
49 quadros vermelhos, 55 azuis e três eventos de recuperação; não é teste do osu!
real ou garantia de FPS sustentados. Nunca executar --fullscreen no CI.

O argumento opcional `--worker <caminho>` usa um worker separado em vez da classe
em memória, com token sintético, origem do app e porta efêmera no loopback. Usar
cópia isolada do executável para não gravar logs na pasta de distribuição. O
single-file assinado passou (6 vermelhos/55 azuis, duas notificações observadas).
Outro ensaio da classe com identidade de monitor validada passou49/56 e três
eventos. A quantidade de notificações observadas não mede FPS ou tempo de recuperação.

test_stream_native.ps1 também confere a ponte GetCaptureMonitors/BeginDesktopCapture:
monitor inexistente deve falhar sem iniciar captura de outra tela. Usa apenas
a própria janela para os demais testes nativos e mantém autenticação obrigatória.

## Entrada e captura de streaming (31/10/2026)

`npm test` testa a oferta recebida 12 s antes de abrir o canal, o prazo separado
de join, limpeza de timers, socket com worker morto/cancelamento durante consulta,
requestFrame por imagem com fallback e vídeo de navegador com áudio por processo
sem criar canvas JPEG ou duplicar o som. StreamingTests no CI cobre cadência
30/60/120 sobre 60/120/144 Hz com jitter, retomada sem rajadas, saída do worker e
propriedade da sessão híbrida, inclusive transição posterior para WGC.

Com app principal fechado, o teste interativo também aceita builds de desenvolvimento:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_stream_native.ps1 -BuildDirectory bin/StreamingPreview/net8.0-windows -WorkerDirectory src/CaptureWorker/bin/Release/net8.0-windows10.0.19041.0
```

Copia somente binários/dependências e frontend para uma pasta nova em bin; não
copia Data. O pacote oficial contém apenas a skin padrão; builds de desenvolvimento
podem incluir as skins presentes no próprio wwwroot. Captura só essa janela de teste e verifica
cliente tardio com cena parada, três inicializações, autenticação, áudio e navegação.
O ensaio animado registra FPS de fonte, codificados, recebidos e decodificados com
receptor visível, pois receptor oculto pode reduzir decodificação. Também exercita
vídeo de canvas sintético pelo caminho de navegador com áudio nativo real da própria
instância; não automatiza o seletor de tela pessoal. Esses números são amostras
locais, não aprovação de taxa sustentada em jogos/1440p ou redes dos amigos.
`XENNEX_NATIVE_SMOKE_ONLY=1` mantém os testes de inicialização/segurança/áudio e
mede apenas o caminho híbrido Full HD/60, sem repetir os três ensaios WGC animados.
O pacote final passou nesse modo: 1920×1080, 54,7 FPS decodificados e um áudio ativo;
ensaio anterior 720p mediu 59,1 FPS. Sem captura pessoal nem emissão real de TURN.

## TURN opcional (31/10/2026)

`npm test` em frontend inclui `turn-fallback.test.mjs`, que testa o cliente e o Worker
com API Cloudflare simulada: validação/expiração, auth/origens, rate limit, TTL,
segredos ausentes das respostas, cancelamento e serviço desligado sem consultas.
A suíte de salas cobre isolamento do PeerJS e renovação sem reiniciar outros peers.
O browser-streaming.mjs usa um endereço de relay sintético inválido para verificar
opt-in, renovação e manutenção de P2P real. Não há emissão real de credenciais ou
validação de retransmissão Cloudflare nesses testes. Ensaios e ativação externa:
[STREAMING_TURN.md](STREAMING_TURN.md).

## Interação das transmissões (31/10/2026)

Em frontend, npm test cobre as oito direções de resize com borda oposta ancorada,
limites e amostras RTP indisponíveis/zeradas/reiniciadas. Após npm run build:web,
sirva cloudflare_pages/dist no loopback e execute tests/browser-streaming.mjs com
XENNEX_TEST_URL apontando para esse endereço (padrão http://127.0.0.1:5179).
O script usa três publicadores sintéticos e sinalização PeerJS real; verifica
diálogo de fontes em desktop/celular, controles em Somente telas, preenchimento
vertical, movimento até a parte inferior, resize superior esquerdo/teclado,
duplo clique para destaque, FPS recebidos não fictícios e preservação de áudio/
volume ao alternar layout, além da migração da coordenação. Imagens de verificação
ficam em bin/streaming-qa. Nenhuma tela, câmera ou microfone pessoal é capturado.
Em ambiente que bloqueia o Edge de teste, usar a permissão de execução adequada
também para o servidor local; não confundir falha de inicialização com regressão.

run_dev.ps1 -StreamingPreview -BuildOnly gera o teste nativo isolado sem abrir o
app. Os testes locais não garantem 60 FPS ou 1440p sustentados entre redes reais.

## Laboratório opcional de memória neural da Alice

python -m scripts.alice_memory.continuous_recall_experiment --output <pasta-nova>
--seed 41 recebe situações/pistas por observe, com intervalos simulados0,2/0,1s
sem limpar o estado de trabalho. Replicar com53/89. Critérios e resultados de
desenvolvimento reprovados estão em ALICE_EPISODIC_CONTEXT.md;3 sementes reservadas
passaram48/48,24/48 com pesos zerados. Cada avaliação parte do mesmo snapshot e
adiciona32 impressões; nenhuma pista nova recebe áudio lembrado como observado.
O runner sai1 se os critérios não passarem. Auditorias separadas em processo novo
passaram48/48 nos arquivos novos e48/48 nos antigos, sem reaprender a preferência.
Política2 versiona a regra de leitura; política1 mantém leitura antiga. CI/build
e28 testes direcionados passaram. Artefatos continuous-recall-* em bin/AliceMemory.

python scripts/tests/test_alice_contextual_recall.py cobre8 contratos de contexto
anterior, feedback externo/único/expirado, preservação factual, retirada de momentos,
modo desligado, restauração pendente, saturação sem bloquear créditos recentes,
leitura antiga/nova e rejeição de estados adulterados. Passaram
também9 reativação e11 runtime, além de CI/build Release no incremento contextual.

python -m scripts.alice_memory.contextual_recall_experiment --output <pasta-nova>
--seed 17 executa o currículo não verbal (96 feedbacks,CPU1,60s). Repetido com
29/71:16/16 por semente,8/16 sem política/contexto, sem conteúdo ao apagar fatores.
Os relatórios originais precedem a ampliação da checagem de restart no runner;
a auditoria separada contextual-recall-fresh-audit-20261101.json verificou48/48
novas consultas restauradas, sem reaprender preferências. Verificar accepted no
relatório; exit0 sozinho não significa critério atingido. Protocolo e limites em
ALICE_EPISODIC_CONTEXT.md. Sem encoder, LLM, sensores pessoais ou janela nativa.
NativeGrounding10 persiste a política/contextos;1–9 permanecem legíveis.

python scripts/tests/test_alice_native_reactivation.py cobre9 casos de memória
não verbal e modo implícito. Regressões do incremento:15 NativeMoments,13
NativeGrounding,14 NativeQuery e11 RuntimeStore. O ensaio
python -m scripts.alice_memory.native_reactivation_probe --checkpoint <estado>
--output <pasta-nova> usa pista visual de nome aprendido, sem encoder/LLM, lê duas
representações, zera/restaura fatores em controle, ativa estado e verifica restart.
Fonte local nonverbal-reactivation-real-20261101-v2. Não é nova experiência nem
aprovação da seleção contextual/fala livre. NativeGrounding9 preserva modo ligado;
legados não são ativados automaticamente. CLI --native-implicit-recall liga o
experimento; --no-native-implicit-recall desliga. Sem mudança de UI neste lote.

Diálogo: python scripts/tests/test_alice_dialogue.py (25 casos) verifica entrada
de texto, atenção full/quiet, SHA errado, mudança durante expressão, origem self
sem fato automático, fila/processo único, pending/restart, replay, fraude, limite
de histórico e seleção por assunto.33 regressão: feedback_interactions/interactions/
reference_query/ui_gateway;32 de concept_query/native_feedback/context_report.
Todos passaram, além de UI headless, CI0 e build .NET/frontend0.

Em01/11, mais sete controles de associação por nome verificam pesos de nome,
episódio e interpretação, origem/quiet, ambiguidade, revisão/restart e seleção
explícita.25 casos finais/94,186s +14 NativeStream/54,006s, CI e .NET passaram.
UI/frontend acima são evidência do incremento anterior; não houve mudança de UI
neste recorte. Encoder falso do teste de diálogo usa RAM simulada, evitando que
outros aplicativos alterem o teste semântico; admissão real permanece intacta.
Probe dialogue_auto_probe usa encoder real e4B, parser original preservado.
dialogue-auto-real-20261101-v1 não adquiriu nova entrada por RAM (19 adiamentos).
Lookup isolado sobre a origem, sem encoder e com gate de atenção sintético,
também não passou no positivo: hami evoca dois episódios. Não declarar integração
real aprovada. Diagnóstico e contrato seguinte em ALICE_EPISODIC_CONTEXT.md.

Os três casos adicionais do comparador verificam contextos determinísticos,
abstenção com pesos apagados apesar de fala gerada, restauração dos pesos em
falha e registro de erros do backend sem aprovação de qualidade. A avaliação
real usa probe_alice_feedback.ps1 -Probe dialogue_model_probe com um checkpoint
contextual e pasta nova por modelo instalado. Não abre janela nem usa sensores;
oito casos de linguagem não validam aprendizagem ou conversa geral. Resultados
de13/10 e revisão manual: [ALICE_DIALOGUE_COMPARISON.md](ALICE_DIALOGUE_COMPARISON.md).

Seleção separada acrescenta quatro casos: fala com modelo próprio sem reescrita
da memória/parser, pending com escolha antiga após restart, migração de fila1 e
recusa atômica de nome inválido, runtime de LanguageCoordinator legado. Testados
17 juntos e o novo legado separadamente;12 regressão de interação e10 runtime_store.
AlicePanelTests cobre padrão compatível e nome inválido antes de iniciar processo.
Headless UI verifica edição/serialização independente dos dois campos.
probe_alice_feedback.ps1 -Probe dialogue_selection_probe -Model qwen3.5:4b usa
texto já adquirido com tópico selecionado, runtime180s e reset da seleção em novo
processo. Conserva registro histórico4B/parser0,8/contadores/pesos/origem. Artefato
dialogue-selection-real-v1 aprovado para integração, quality_approved=false.
No terminal, --dialogue-model=qwen3.5:4b seleciona a fala; --dialogue-model=
volta ao parser, preservando argumento vazio em PowerShell. Omitir a opção mantém
a seleção do checkpoint. Auditoria independente preservou384 bancos anteriores.

probe_alice_feedback.ps1 -Probe dialogue_probe usa encoder Gemma2 e Qwen instalada
sem GUI/sensores. dialogue-real-v2 confirma3 textos adquiridos e diálogos restaurados.
Qualidade livre permanece não aprovada; consultar partial/report.json e logs de v1/v2.
dialogue_topic_probe é avaliação verbal da mesma evidência de v2 sem novo encoder;
histórico não pertinente removido, pergunta atual priorizada. Uma atribuição correta
não basta para validar toda a formulação gerada.

Painel experimental: python scripts/tests/test_alice_ui_gateway.py valida cópia,
proveniência, identidades/contadores, recusa de preparação parcial/lease alheio,
arquivos selecionados e publicação sem Torch (5 casos). AlicePanelTests integra
CI geral: relatório antigo não implica processo ativo, entrada antes de start e
configuração arbitrária são recusadas; não retomar durante shutdown.
Após npm run build, node frontend/tests/alice-ui.test.mjs valida ponte simulada,
ensino/correção/consulta, referência selecionada, rascunhos, falha e largura reduzida.

probe_alice_feedback.ps1 -Probe panel_runtime_probe -Checkpoint <estado-contextual>
-Output <pasta-nova> -Python <python-com-torch> usa serviço C# real e Qwen instalada
com host próprio, orçamento temporário90%, sem sensores. Artefato de13/10:
panel-service-real-v1/audit.json confirma correção mãe,253/217 constantes e retomada.
Teste nativo: usar scripts/tests/test_local_ai_native.ps1 -BuildDirectory
bin/Release/net8.0-windows -TestScript frontend/tests/alice-native.test.cjs somente
com Xennex fechado e usuário disponível; abre janela e pode disputar foco. Passou
duas execuções write/read em cópia isolada, com COM/runtime reais. Não executar
build principal em paralelo com CI (VrTests também referencia o projeto principal).

Feedback no canal: python scripts/tests/test_alice_feedback_interactions.py (8 casos)
valida ação original após nova situação, valor positivo/negativo, quiet, ausência de
escrita para inválido/vencido/incerto, replay, pending/restart, fraude, fila e ablação.
45 regressão: unittest dos módulos test_alice_native_feedback, test_alice_interactions,
test_alice_context_report, test_alice_reference_query e test_alice_ui_gateway.
probe_alice_feedback.ps1 -Probe feedback_channel_probe usa Qwen instalada e pista
sensorial sintética, sem GUI/sensores. feedback-channel-real-v1/report.json confirma
aprovação de quiet, uma atualização, rejeição de duplicação e restauração.

Consulta por mensagem: python scripts/tests/test_alice_reference_query.py cobre
perspectiva sem memória no parser, fonte original já corrigida, ausência de contexto,
perda de episódio sensorial, interpretação apagada, correção antes da confirmação,
percepção não inventada, pending/restart/fallback, pai/mãe e fila nominal/referenciada
mista. Oito direcionados/28,525 s;199 nativos +98 coordenação, mais um caso novo após
coleta =298 distintos; CI0. Falha de regex inicial fica preservada.

probe_alice_feedback.ps1 -Probe reference_query_probe -Checkpoint <portable-contextual>
-Output <pasta-nova> -Python <python-com-torch> usa Qwen instalada e contexto/memória
perceptiva anterior. reference-query-real-v1 passou no fluxo; benchmark12/14 continua
accepted=false. Não carrega encoders novos/sensores. Três retomadas em processo novo
conservam pesos e não chamam modelo/ensinam novamente; apagar interpretação retira
suporte. Audit script em bin/AliceMemory/audit-reference-query.py; hashes/fontes/
artefatos no reference-query-manifest.json. Referência à mensagem é fornecida, não
resolução geral aprendida de pronomes/conversa.

Contexto sem IDs no texto: python scripts/tests/test_alice_context_report.py verifica
parser sem memória, fragmentos literais/guardas, demora/nova cena, pai/mãe, reenvio/
fallback, ref passada alterada, job retirado, alvo esquecido, fonte linguística,
modalidade não atendida, poda protegida, peso apagado e recusa de versão substituída.
Dez contratos/23,565 s.199 nativos +91 coordenação =290 testes, CI final0.
Teste NativeStream de parada agora força save_every3600: confirmação exige dois
snapshots terminais antes de liberar cópia; shutdown não avança cognição.

probe_alice_feedback.ps1 -Probe context_report_probe -Checkpoint <portable-real>
-Output <pasta-nova> -Python <python-com-torch> usa Qwen instalada e memória perceptiva
real anterior; não carrega novos encoders/sensores. context-report-real-v3 passou
na integração; benchmark integral14/16 accepted=false (antes10/16 e12/16). Não
aprovar português geral nem esconder recusas; guardas/candidatos são fornecidos.
Três retomadas frescas sem modelo preservam pesos/nomes/relatos e não repetem ensino;
apagar novos pesos retira resposta sem alterar antigos. Artefatos, falhas e versões
de fonte no context-report-manifest.json; auditor em bin/AliceMemory/audit-context-report.py.

Relatos ao vivo: test_alice_interactions.py agora12 contratos, incluindo relato,
correção e comparação; pending/restart/fallback, backpressure, migração1→2, resultado
alterado e evidência que perde validade durante o duplo commit.199 nativos +12 do
canal +43 conceituais/retenção =254 testes verificados; CI final0.
probe_alice_feedback.ps1 -Probe interaction_report_probe usa encoders instalados
para imagem/áudio de arquivos públicos em processos sucessivos e Qwen0,8B. real-v3
passou; real-v1/v2 ficaram preservados (reserva de RAM/ambiguidade do avaliador).
Não aprovar entrada simultânea nem linguagem aberta com esse resultado. Auditoria
em processo novo do portátil/atual/anterior confirma nomes/pesos anteriores, versões,
reenvio sem reensino, ausência de modelo e abstenção após apagar pesos. Script do
ensaio e artefatos em bin/AliceMemory/audit-interaction-reports.py e no manifest
interaction-report-manifest.json. Pista temporal é fornecida, não descoberta.

Canal durante execução: python scripts/tests/test_alice_interactions.py cobre
cliente sem Torch, limites/locks/UUID, duas gerações antes do recibo, reenvio sem
reensino, dúvida e resposta após nova cena, espera por frame exato, consulta sem
aprendizado, migração e corrupção de vínculo/hash. Sete contratos/22,176 s.
Probe finito: probe_alice_feedback.ps1 -Probe interaction_runtime_probe -Checkpoint
<arquivo> -Output <pasta-nova> -Python <python-com-torch>. Usa modelo local real e
encoder sensorial de teste, clientes separados após início; não ativa sensores.
interaction-runtime-real-v1 passou, duas gerações retomadas em processo novo sem
modelo/duplicação.213 regressões/442,003 s,36 conceituais/59,434 s e CI final0.
Confirmar metadados do alvo não comprova discriminação visual real ou chat aberto.

Esclarecimento: `test_alice_native_name.py` cobre palavra/foco após nova cena e31 s,
horário da resposta, origem sem modelo, ambiguidade, contexto expirado/esquecido,
duplicação, retomada e fila legada. `probe_alice_feedback.ps1 -Probe
native_name_reply_probe -Checkpoint <arquivo> -Output <pasta-nova> -Python
<python-com-torch>` testa recusa real da Qwen e resposta controlada ligada ao áudio
anterior. Não aprovar entendimento geral porque a recuperação contextual passou.
Retomada em processo novo do portátil e duas gerações conserva resposta/prova.
206 regressões/318,988 s,14 contratos direcionados/18,156 s e CI0.

Ensino de nomes: `python scripts/tests/test_alice_native_name.py` verifica literal
posterior ao predicado, NFKC/casefold, canal atendido, pergunta/negação, ref original
durante mudança de frame, alvo esquecido, quiet, fila única, retomada e migração.
`probe_alice_feedback.ps1 -Probe native_name_probe -Checkpoint <arquivo> -Output
<pasta-nova> -Python <python-com-torch>` usa modelo instalado e host local próprio,
sem downloads. `-Model` permite comparar os já presentes. Benchmark completo
continua falhando:0,8B13/15, Qwen4B14/15 e Gemma4B14/15. Não relaxar accepted nem
confundir aprendizado de três associações sintéticas com linguagem geral aprovada.
Artefatos v6 mostram nomes persistidos e restart portátil/atual/anterior sem replay.
202 regressões/286,062 s, dez contratos de nomes,36 conceituais e CI final0.

Retenção de correspondências: `python scripts/tests/test_alice_semantic_retention.py`
verifica intervalo particionado, perda parcial de detalhe versus componente reforçado,
familiaridade sem cobertura suficiente, reexposição/transferência contra início frio,
três bases rotacionadas, origem sem replay, retomada/migração e âncoras inválidas.
`python -m scripts.alice_memory.semantic_retention_probe --output <pasta-nova>
--checkpoint <checkpoint-portátil>` produz ensaio finito sintético e migração opcional
de checkpoint real, sem carregar LLM/encoder. Tau10 s e gap300 s são acelerados;
padrão86400 s. Não generalizar associação sintética para memória conceitual humana.
Regressão conjunta de `test_alice_native*.py` e retenção:192 testes/278,135 s, CI0.

Feedback português: `python scripts/tests/test_alice_native_feedback.py` verifica
proposta/proveniência, negação, palavrões, incerteza, origem externa, worker único,
crédito social sem benefício/esforço inventados e retomada sem escrita duplicada.
`probe_alice_feedback.ps1 -Python <python-com-torch> -Output <pasta-nova>` avalia
Qwen local em checkpoint copiado e encerra seu host próprio11438. Não baixa modelo;
precisa do modelo já instalado e acesso local ao inventário de processos Windows.
Ensaio final v8:18/18 frases, incluindo restrições/glossário fornecidos, duas
escritas e duas abstenções. Não generalizar esse conjunto para conversa aberta.
Regressão nativa185 casos; CI0. Retomada current/previous/portátil conserva pesos
e fontes sem carregar modelo; tentativas anteriores ficam preservadas em bin.
Teste de cancelamento simula publicação atômica interrompida e verifica que arquivos
fora da pasta do worker continuam intactos.12 consultas conceituais e16 contratos
de coordenação passaram após corrigir a limpeza do arquivo temporário.

Impacto da conseqüência: `python scripts/tests/test_alice_native_impact.py`
verifica valor aprendido/retido, controle apagado, importância negativa/positiva,
esquecimento, slot reutilizado, feedback inválido/duplicado, quiet, fontes e estado
afetivo compartilhado. `native_impact_probe.py` percorre a fila real de arquivos em
cópias de runtime/inbox com encoder offline e conseqüências roteirizadas. Conferir
episódios/valores/fontes/reinício, sem inferir sentimento humano ou verdade factual.

Contexto nas correspondências: `python scripts/tests/test_alice_native_link_context.py`
verifica mesma pista/resultados diferentes, contextos reservados, estado anterior
ao alvo, primers pelo fluxo real, migração e rollback das direções gerais/contextuais.
`native_link_context_probe.py` avalia variantes de arquivos controlados com
recibos congelados verificados. Nenhum rótulo de contexto/alvo entra no predictor;
comparar contra associação geral, camada apagada e retomada. Ainda não avalia
entendimento de situações abertas do cotidiano.

Correspondência sem nome: `python scripts/tests/test_alice_native_links.py`
verifica pares aprendidos, transferência reservada, episódio esquecido, canal
ausente, surpresa antes do update e integração no estado compartilhado.
`native_links_probe.py` usa recibos locais verificados de ensaios controlados
anteriores, sem carregar encoder/LLM ou tocar em sensores. Pareamento trocado,
pesos apagados, retomada e comparação com copiar o latente da pista são controles
separados; não comprovam compreensão de áudio/imagem cotidiana.

Retenção nativa limitada: `python scripts/tests/test_alice_native_retention.py`
verifica aprendizagem depois de lotação, IDs de vida, associação sobrevivendo ao
episódio, relatos corrigidos sem imagem/áudio original, rollback e recuperação
das duas gerações. `native_retention_probe.py` executa ensaio finito em cópias de
runtime/inbox, reduzindo somente o arquivo de ensaio. Não acessa sensores ao vivo.
Esquecimento gradual de conhecimento e significado pessoal exigem outros ensaios.

Com as dependências de `scripts/requirements-alice-memory.txt` disponíveis em
ambiente separado do Gestures, execute na raiz:

```powershell
python scripts/tests/test_alice_memory.py
python scripts/tests/test_alice_streaming_memory.py
python scripts/tests/test_alice_temporal.py
python scripts/tests/test_alice_context_memory.py
python scripts/tests/test_alice_loop.py
python scripts/tests/test_alice_crossmodal.py
python scripts/tests/test_alice_predictive_loop.py
python scripts/tests/test_alice_language.py
python scripts/tests/test_alice_episodic.py
python scripts/tests/test_alice_continuous_mind.py
python scripts/tests/test_alice_temporal32.py
python scripts/tests/test_alice_temporal_mind.py
python scripts/tests/test_alice_consolidation.py
python scripts/tests/test_alice_paged_memory.py
python -m unittest discover -s scripts/tests -p 'test_alice_*.py'
python -m scripts.alice_memory run
python -m scripts.alice_memory stream
python -m scripts.alice_memory time
python -m scripts.alice_memory context
python -m scripts.alice_memory loop --steps 10000
python -m scripts.alice_memory crossmodal
python -m scripts.alice_memory predictive-train --models <models.pt>
python -m scripts.alice_memory predictive-loop --models <models.pt> --steps 10000
python -m scripts.alice_memory episodic --seed 17
python -m scripts.alice_memory memory-action --checkpoint <session.pt> --seed 17
```

São testes de treinamento real em CPU, com sinais sintéticos, novas associações,
entradas reservadas para avaliação, controles e consulta em processo novo sem
dataset. Não requerem câmera, microfone, rede ou modelos pré-treinados. O
segundo recorte verifica acontecimentos sequenciais sem replay, correcao que
preserva a interpretacao inicial, abstencao em contexto nao aprendido e
equivalencia numerica entre atualizacao online e regressao regularizada em lote.
O terceiro verifica antecipacao causal com estado recorrente, ordem, intervalos,
ausencia de medicao, pausas e retomada em processo novo sem historico.
O quarto liga contexto temporal a blocos associativos, separa importancia,
frescor e reativacao, limita leituras e testa lotacao sem apagar experiencias.
O laboratório é opcional e não adiciona PyTorch ao CI base nem ao app distribuído.
O ciclo causal verifica ações/feedback, filas limitadas e retomada do mundo/agente
em processo novo. O ensaio contrastivo verifica correspondência, máscaras e
antecipação latente condicionada à ação. O ciclo preditivo verifica restauração
do núcleo aprendido, previsão
causal pontuada, registros multimodais separados e estabilidade em execução longa.
Qualidade preditiva é critério separado: estabilidade não demonstra boa previsão.
O recorte episódico testa cenas/sons compostos, fronteiras aprendidas, oclusões,
recuperação por pistas parciais, abstenção, revisão dirigida e consulta em processo
novo. A política de memória tem controles sem memória, memória trocada e referência
treinada com somente a pista atual. Os símbolos e significados são ensinados no
currículo sintético; não é reconhecimento de fala, emoções humanas ou cenas reais.
Testes de linguagem usam transporte
simulado e não carregam LLM. A comparação real opcional é
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/probe_alice_language.ps1`:
usa Gemma já instalado, lembranças sintéticas e servidor próprio finito, com
orçamento de RAM; não integra ainda a linguagem ao ciclo nem demonstra mudanças
de personalidade. Artefatos e comandos estão no guia do laboratório.
O mesmo script com `-Source episodic -Checkpoint <session.pt> -Image <cue.png>`
e os limites opcionais `-WindowStart`/`-WindowEnd` compara interpretações episódicas,
formulações sugestivas e relações sem evidência. Omissões de atributos disponíveis
são rejeitadas. A comparação pode ser recusada pelo orçamento de RAM; esse resultado
não comprova a influência do pré-treino. Texto livre ainda precisa de revisão.
O CI geral continua obrigatório. Contrato e resultados em
[ALICE_NEURAL_MEMORY.md](ALICE_NEURAL_MEMORY.md).

O mind contínuo testa consequência atribuída à ação, valor específico por objetivo,
controle de ruído/frescor, retorno próprio sem recompensa inventada, evocação interna,
datas preservadas, limitação de filas, pausa sem observação e retomada sem histórico
em processo novo. Experimentos finitos adicionais:

```powershell
python -m scripts.alice_memory.importance_experiment --checkpoint <actor.pt> --output <pasta-nova>
python -m scripts.alice_memory.continuous_experiment --checkpoint <mind.pt> --output <pasta-nova> --realtime
```

O segundo mede scheduler e recursos em repouso, usando um thread de inferência;
estabilidade e metas de CPU/latência/RSS aparecem separadas. Não ativa fontes reais
nem inicia daemon. O conjunto ativo usado no controle de valor não é compressão
física ou política de descarte ao encher a memória.

Antecipação 32-d: testes de causalidade, ausência de input, propósito de ação,
compatibilidade sensorial, fontes, checkpoints em processo novo e scheduler com
núcleo preservado. Fixtures unitárias temporais são intencionalmente não treinadas;
elas validam contratos, sem afirmar qualidade. Avaliações treinadas separadas:

```powershell
python -m scripts.alice_memory.temporal32_experiment --checkpoint <actor.pt> --output <pasta-nova> --seed 17
python -m scripts.alice_memory.temporal_runtime_experiment --checkpoint <actor.pt> --models <models.pt> --output <pasta-nova> --seed 17
python -m scripts.alice_memory.temporal_continuity_experiment --checkpoint <actor.pt> --models <models.pt> --output <pasta-nova> --seed 17
```

Loader temporal exige formato 20 e relatório aceito. Checkpoint integrado é 21;
o scheduler conserva esse formato. Comparação usa GRU com orçamento equivalente,
reset de estado e ações embaralhadas. Encontros sucessivos consultam fatos antigos
por pista parcial/janela após novos eventos sem reset. Limites e resultados no
plano/laboratório; geração sintética não demonstra português, pessoas reais ou
atividades sobrepostas. Não ativa sensores nem altera dados pessoais.

Consolidação compartilhada testa extração do alvo dos pesos episódicos, ausência
de alvo no input, uma atualização por fonte/revisão, conflitos e desconhecimento,
retorno próprio, invalidação de checkpoints/RNG, processo novo e leitura factual
pela linguagem mesmo com expectativas discordantes. Qualidade é avaliada à parte:

```powershell
python -m scripts.alice_memory.consolidation_experiment --checkpoint <actor.pt> --models <models.pt> --output <pasta-nova> --seed 17
```

Compara desconto 0,9 versus acumulador e pesos semânticos zerados. Currículo/
retenção/adaptação e combinações reservadas estão no plano. Checkpoint integrado
é 23; formato experimental 22 da variante falha não é migrado silenciosamente.
O scheduler conserva estado temporal/semântico e verifica que idle não duplica
escritas. Custos dos bancos globais não incluem os episódios, que seguem residentes.

## Abrir o código atualizado

Feche a instância antiga do Xennex antes de testar: o aplicativo permite uma
única instância e pode restaurar a antiga em vez de abrir o build novo.

Na raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_dev.ps1
```

O script compila a interface, o aplicativo e o CaptureWorker e abre
`bin/Release/net8.0-windows/Xennex.exe`. Use `-BuildOnly` para apenas compilar.
Este é um build de desenvolvimento e depende do .NET instalado. Para distribuir,
use exclusivamente `scripts/package_release.ps1`.

O executável antigo da raiz não é substituído pelo build de desenvolvimento.
As configurações deste build ficam em `bin/Release/net8.0-windows/Data/`;
os dados pessoais de `Data/` na raiz não são copiados nem modificados.
O frontend e as skins são copiados pelo build. O script de gestos e o `REAL.exe`
local, quando existente, também ficam disponíveis na saída de desenvolvimento.

## Roteiro manual

- Abrir o app, navegar por todas as abas, redimensionar e arrastar a janela.
- Ativar/desativar sidebar, mudar posição e testar auto-hide das duas barras.
- Trocar e editar skins, incluindo imagem, vídeo, bordas e cores.
- Fechar, minimizar à bandeja, restaurar e encerrar completamente.
- Iniciar/parar REAL e testar Wacom no ambiente com os drivers disponíveis.
- Testar câmera, gravação/exclusão de gestos e configuração de swipe.
- Abrir sala, transmitir janela/tela com áudio, entrar pelo visualizador e navegador.
- Parar/reiniciar a transmissão; abrir múltiplos visualizadores e encerrar o app.
- Consultar a versão e verificar atualizações. Não instalar uma release antiga
  sobre este build de teste para validar a organização do código.

Gestures usa um motor autocontido nas releases. Em desenvolvimento, execute
scripts/setup_gestures.ps1 para preparar Python/MediaPipe/OpenCV/NumPy;
run_dev.ps1 encaminha esse ambiente ao processo de teste. Consulte
[GESTURES.md](GESTURES.md) para os testes sintéticos e o roteiro com câmera.
O motor REAL e o WebView2 Runtime continuam sendo dependências externas.

## Verificações automatizadas

`StreamingTests` integra `test_ci.ps1`: startup/cancelamento não bloqueantes,
proteção do dono durante resposta tardia/limpeza, isolamento entre janelas,
parada apenas do áudio e conversão real de amostras sem ganho/clipping forçado.
Não abre dispositivo de áudio. `npm test` inclui `capture-lifecycle.test.mjs`
para deadlines, cancelamento de seletor pendente, mídia tardia, interrupção
de socket/worker e configuração ICE aceita. O teste de navegador verifica a
UI de loading/cancelar com WebRTC real; o smoke nativo usa apenas janela e
processo de áudio da instância isolada. Não captura áudio do sistema pessoal.

`VrTests` faz parte de `test_ci.ps1`: valida seleção por IDs, eventos de gatilho
sem coordenadas de release, catálogo sintético de 126 imagens, páginas, pastas,
miniaturas com dimensões limitadas, tamanho/distância, limites de zoom,
renderização RGBA, abertura/fechamento, reabertura, falha de
conexão e cancelamento usando runtime fake, sem headset ou catálogo pessoal.
Para verificar SteamVR real, execute
`dotnet run --project scripts/tests/VrTests/VrTests.csproj -c Release -- --native`.
Este smoke exibe imagens sintéticas por três segundos e encerra os overlays;
não confirma cliques físicos, conforto ou privacidade do espelho. Veja [VR.md](VR.md).

```powershell
cd frontend
npm run build
npm run lint
cd ..
dotnet build Xennex.csproj -c Release
dotnet build src/CaptureWorker/Xennex.CaptureWorker.csproj -c Release
powershell -ExecutionPolicy Bypass -File scripts/tests/test_release.ps1
```

O teste PowerShell cria fixtures dentro de `bin/`, verifica a integridade do
pacote e simula duas cópias de atualização. Não executa o atualizador completo,
não inicia processos de teste, não instala certificados e não toca nos dados reais.

Os testes não substituem a validação de captura, áudio, drivers, câmera,
renderização WebView2 e release assinada em um Windows limpo.
Falhas gerais do backend são registradas em `logs/xennex.log` ao lado do
executável; o atualizador registra falhas em `%TEMP%/xennex_update_error.log`.

## Biblioteca de artes

Depois de compilar o frontend, execute os testes de catálogo/arquivos e de UI:

```powershell
dotnet run --project scripts/tests/AssetLibraryTests/AssetLibraryTests.csproj -c Release
node frontend/tests/assets-ui.test.mjs
```

`scripts/tests/test_ci.ps1` inclui AssetLibraryTests. Para verificar a ponte COM,
WebView2, SQLite, miniatura e persistência em uma cópia isolada do app, feche a
instância principal e execute `scripts/tests/test_assets_native.ps1`; requer a porta
9232 livre. Fixtures ficam em `bin/`, sem alterar `Data/` pessoal. Consulte
[ASSET_LIBRARY.md](ASSET_LIBRARY.md) para limites e roteiro manual.

## Streaming 0.2.x

Veja [STREAMING.md](STREAMING.md) para o build isolado, testes de salas e roteiro
de captura nativa, navegador e redes distintas.

A assinatura do pacote é verificada por WinVerifyTrust e pelo certificado esperado.
`scripts/tests/test_signature.ps1` valida assinatura íntegra, assinante incorreto e
adulteração usando arquivos temporários; exige o certificado local do projeto.
O empacotador aceita especificamente a raiz local não confiável, sem instalar
certificados no Windows, e rejeita as demais falhas de assinatura.

## Jogos — biblioteca e histórico manual

```powershell
dotnet run --project scripts/tests/GameAnalyticsTests/GameAnalyticsTests.csproj
# Após npm run build; exige Playwright com Edge instalado.
node frontend/tests/games-ui.test.mjs
```

O teste visual aceita PLAYWRIGHT_MODULE apontando para uma instalação existente.
Ele usa uma ponte simulada, dados fictícios, exportação/importação e capturas
em bin/game-ui; o teste C# usa diretório temporário exclusivo.
Verificar no app: adicionar jogo, salvar registro, reiniciar, editar, comparar
dois registros, filtrar datas e exportar/importar como cópia.
Os testes não validam integrações externas, pois ainda não foram implementadas.

Para testar a ponte COM e reabrir uma cópia isolada do executável já empacotado:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/tests/test_games_native.ps1
```

Exige Node, Playwright (ou PLAYWRIGHT_MODULE) e a porta local 9231 livre.
A cópia de teste fica em bin/GameNativeSmoke-*; não copia nem acessa Data pessoal.
Encerre outras instâncias do Xennex antes desse teste nativo.

Teste visual adicional de jogos:

node frontend/tests/games-visual.test.mjs

Usa as mesmas dependências e dados isolados do teste games-ui.

Para definições livres de jogos, sequências de ações e agrupamentos por contexto:

```powershell
node frontend/tests/games-definition.test.mjs
```

Usa a mesma instalação Playwright e dados fictícios isolados dos outros testes.
O teste nativo também verifica skills, campos de cenário e resultados de ações
ao reabrir o executável.

## IA local

Testes de política, fila, persistência, cancelamento e protocolo sem baixar modelos:

```powershell
dotnet run --project scripts/tests/LocalAiTests/LocalAiTests.csproj
```

Teste nativo com respostas simuladas por servidor HTTP loopback. Requer Playwright,
WebView2 e porta 9232 livre; feche outras instâncias do Xennex. Configurações e
histórico ficam em uma cópia única bin/LocalAiNative-*; não usa Data pessoal.

```powershell
cd frontend
npm run build
cd ..
dotnet build Xennex.csproj -c Release -o bin/LocalAiDev
powershell -ExecutionPolicy Bypass -File scripts/tests/test_local_ai_native.ps1
```

PLAYWRIGHT_MODULE pode apontar para um pacote Playwright já instalado. O teste
verifica a ponte COM real, catálogo, streaming, troca de aba, exportação, fila por
orçamento, cancelamento, rascunho, layout compacto e persistência após reinício.
A telemetria usa o Windows real; geração usa fixture, não benchmark de modelo.
Para validar desempenho real, use um servidor local compatível em /v1, carregue
um modelo, configure reservas incluindo contexto/buffers e compare consumo antes,
durante e depois. Limites do aplicativo são cooperativos: cancelar HTTP não garante
liberar memória do motor. Priorizar meu PC interrompe a resposta e pausa a fila.

O conjunto de IA também cobre Ollama NDJSON, metadados, contexto, recusa de modelo
remoto, reservas de modelo residente, observações persistidas e cancelamento na
consulta de metadados. O teste nativo seleciona Ollama em cartões, salva orçamento
automático, conversa pela ponte COM e verifica layout compacto.

Teste opcional com o motor iniciado pelo próprio serviço do Xennex, usando apenas
um modelo já instalado:

```powershell
dotnet run --project scripts/tests/LocalAiTests/LocalAiTests.csproj -- --owned-real llama3:latest
```

Exige Ollama no caminho padrão e porta 11436 livre. Cria dados temporários, usa
contexto 2048, saída 128, limite 85%, executa duas mensagens e confirma reutilização
de pesos e descarregamento. Encerra somente o processo iniciado pelo teste. Se o
PC estiver sem margem, pode expirar aguardando recursos; não aumente os limites
para ocultar esse resultado. O teste não altera configurações pessoais do app.

## Editor de skins

Ver docs/SKINS.md. Testes puros: scripts/tests/SkinTests; integração nativa:
scripts/tests/test_skins_native.ps1 (dados isolados, duas inicializações).
Validar também manualmente um vídeo local, o seletor de arquivos do Windows e
o modo compacto no monitor do usuário; a integração automatizada não escolhe
arquivos no diálogo nativo nem mede decodificação de mídia na GPU.
## Salas e especialistas locais

```powershell
dotnet run --project scripts/tests/LocalAiTests/LocalAiTests.csproj
powershell -ExecutionPolicy Bypass -File scripts/tests/test_local_ai_native.ps1 -TestScript frontend/tests/ai-rooms-native.test.cjs
dotnet run --project scripts/tests/LocalAiTests/LocalAiTests.csproj -- --rooms-real llama3:latest
```

A suíte tem 104 verificações: migração com backup original, isolamento direto de
contexto, autoria, seleção de modelos, rodadas sequenciais, memória proposta,
idempotência, cancelamento/falha de dependências e restauração sem repetição.
O teste nativo exige todas as janelas Xennex fechadas e PLAYWRIGHT_MODULE conforme
acima; usa dados isolados, ponte COM e servidor controlado. Cobre cadastro,
plano/permissões, reunião, execução individual, comparação, proposta/exportação
de caderno e reinício.

O teste real exige Ollama instalado, llama3:latest já em disco e porta 11436 livre.
Não baixa modelos. Usa contexto 4096, saída 128 e orçamento padrão de 75%, confere
17 + 25 em dois especialistas e reutilização do modelo, depois libera os modelos
mesmo sem modelo global selecionado. Encerra apenas sua instância do motor.
É uma verificação funcional; não mede qualidade para tarefas complexas.
Regressões de contexto: HistoryTests cobre o caso Nissi com resposta longa e
contexto 4096, ordem/autoria, exclusão de tentativas falhas, UTF-8 e auditoria.
Teste opcional --conversation-real <modelo> avalia conversação e uma proposta de
memória confirmada no teste, com histórico desligado na recuperação. Mantém
artefatos em bin/AiConversationReal-*. Pode falhar por qualidade do modelo; não
confundir resultado com testes determinísticos da infraestrutura. Defina
OLLAMA_MODELS para o diretório preparado antes de executar com modelos novos.

## Painel compacto

Veja [COMPACT_MODE.md](COMPACT_MODE.md) para os testes de geometria, WPF e
interface. O teste nativo percorre os monitores conectados em uma janela
isolada, incluindo bordas compartilhadas, fixação e posição personalizada;
não encerra o Xennex pessoal. Apenas a geometria é executada no CI.

A integração real está em scripts/tests/test_compact_native.ps1, após build
para bin/CompactDev. Exige o app fechado, usa Data/skins isolados e restaura
o cursor. Verifica o viewport nativo nas três direções, canvas fixo, ponte COM,
prévia e salvamento de skin dentro do compacto. Não emula o tamanho da janela.
O teste de navegador também cobre chat/rascunho ao expandir e watch.html.

## CI e regressões de segurança

O workflow `.github/workflows/ci.yml` executa builds React/web/.NET, `npm test`
e `scripts/tests/test_ci.ps1` em Windows, sem aplicativo aberto ou chave privada.
O teste de supervisor Gestures recebe automaticamente o executável Python
resolvido pelo runner. Não há câmera, controle real do desktop ou modelos locais.
A execução remota começa após commit/push; não publica releases.

Veja [revisão de segurança](SECURITY_REVIEW.md) para o escopo, limites da validação
de updates e testes locais de WebSockets/WebView2.


### Captura: redução GPU antes do readback (01/11/2026)

`CaptureWorkerTests` no CI valida geometria, telemetria limitada, serialização do
socket e recuperação com fontes falsas, sem acessar GPU/tela. Ensaio opt-in:

```powershell
dotnet run --project scripts/tests/CaptureWorkerTests -c Release -- --gpu
```

Cria somente texturas sintéticas (sem capturar monitor, abrir janela ou salvar
imagens). Confere cores, rotação, resize, checkerboard/gradiente, JPEG independente,
fallback em WARP10 e compara CPU/GPU com mesma origem4K/saída1080p/JPEG95. Número
não representa FPS recebido nem todos os tipos de conteúdo. Não adicionar `--gpu`
a runners sem GPU. Teste nativo isolado inclui WGC480p, socket autenticado,
decode/canvas e medições reais; `--fullscreen` continua sendo teste interativo
separado que toma foco e exige autorização.


### Decode, fila local e osu! real (01/11/2026)

`npm test` inclui frame-processing.test.mjs: último quadro pendente, uma operação
ativa, fechamento de recursos, cancelamento tardio, fallback de API/canvas e
métricas RTP com reset/ausência de contadores. CI C# simula reinícios infinitos
com um quadro válido por abertura e confere aviso/limite. Não abre jogos.

Comparação de JPEGs sintéticos na WebView2 isolada (app principal fechado):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_stream_native.ps1 -DecoderBenchmark
```

Teste opcional de jogo REAL, exige autorização e osu! em primeiro plano. Captura
explicitamente o monitor do jogo no modo DXGI; Alt+Tab pode mostrar conteúdo do
monitor até o cancelamento. O probe verifica foco a cada25ms, descarta resultados
fora do jogo e encerra o worker. Não salva imagens, títulos ou nomes de mapas:

```powershell
dotnet run --project scripts/tests/CaptureWorkerTests -c Release -- --osu --worker "E:\Projetos e apps\Xennex\Xennex.CaptureWorker.exe"
# Para comparar só a janela WGC, uma etapa de60FPS:
# acrescentar --wgc
```

O teste DXGI mede≈9s por alvo30/60/120, aguarda até90s pelo foco e limita todo o
trabalho. Não força fullscreen nem muda configurações. Reinicializações repetidas
ou ausência de imagens falham explicitamente. FPS medidos no socket não equivalem
a FPS decodificados pelo amigo. Logs da sessão: bin/osu-real-capture.log,
bin/osu-real-wgc.log (fullscreen), bin/osu-real-windowed.log (contorno validado).
