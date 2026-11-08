# Encoder nativo — protótipo isolado (03/11/2026)

Contrato das etapas E01/E02 do [plano de streaming](STREAMING_PLAN.md).
O caminho de captura em produção continua JPEG/canvas/WebRTC. Este protótipo
não oferece um encoder novo na UI, altera salas ou exige instalação dos amigos.

## Primeira implementação

Usar Media Foundation como primeiro candidato comum do Windows e consultar MFTs
de hardware por adaptador via MFTEnum2/MFT_ENUM_ADAPTER_LUID, com fallback de
inventário quando não suportado. DXGI identifica adaptadores disponíveis; marca
não significa suporte. Consultar H.264 primeiro, depois HEVC/AV1 como candidatos.
Separar enumerado, ativado, aceitou perfil e codificou quadros reais.

O primeiro ensaio deve usar somente texturas NV12 sintéticas, D3D11 e encoder
H.264. Não captura desktop/janela/câmera, injeta em jogo ou altera driver. Variar
perfil suportado sem prometer 1080p120. Medir entrada, saída, tempos e recursos,
e conferir bitstream produzido com decoder independente antes da integração.

Executar em processo de teste separado (`scripts/tests/NativeEncoderTests`), com
prazo externo para encerrar driver/transform travado. Não executar esse teste GPU
por padrão no CI. Liberar IMFActivate/IMFTransform/IMFAttributes, eventos,
amostras, texturas, gerenciador DXGI e MFStartup/MFShutdown deterministamente.
Somente depois de passar, mover implementação validada para CaptureWorker/Encoding
e acrescentar a dependência ao Worker de produção.

## Integração posterior

E03 terá contrato próprio para RTP/RTCP/SDP/ICE, relógios/áudio, recuperação,
pressão de rede e fallback. Bytes H.264 de um MFT não podem ser anexados a uma
MediaStreamTrack ou PeerJS sem essa integração. Nem MFT enumerado, textura
aceita ou driver anunciar suporte provam transmissão GPU sem cópia.

## Resultados locais e limites (03/11/2026)

Inventário executado por adaptador e candidato. Um transform enumerado/ativado
ficou sem saída; outro codificou. A enumeração repetiu nomes entre adaptadores
e não forneceu associação verificável do dispositivo. Não inferir suporte de
AV1 na GPU integrada nem selecionar simplesmente o primeiro MFT da lista.

O ensaio H.264 validou 60 quadros coloridos em1920×1080/60 e120 quadros em
1920×1080/120. No segundo, entrada medida≈120,15FPS, intervalo p95≈10,05ms,
primeira saída≈13,44ms (ensaio anterior à integração RTC). Conversão BGRA→NV12 em GPU é executada em cada quadro,
com pool limitado a quatro superfícies e liberação por timestamp de saída.
Decodificador Microsoft independente conferiu todos os quadros e quatro
quadrantes de cor BT.709, incluindo crominância. São texturas sintéticas,
não prova de captura de jogo, entrega WebRTC ou desempenho em outros equipamentos.

Executar explicitamente `scripts/tests/test_native_encoder.ps1 -Encode -Candidate 1
-Color -Width 1920 -Height 1080 -Fps 120 -Frames 120` neste equipamento.
Candidate1 é resultado local, não padrão universal. Runner limita duração e encerra
somente seu processo auxiliar em timeout. Contratos CPU no CI não abrem GPU.

## Transporte nativo experimental

`scripts/build_native_webrtc.ps1 -PrepareTools` prepara compilação portátil
isolada em bin/: libdatachannel0.24.6 por commit fixado, MbedTLS3.6.7 LTS com
DTLS-SRTP e submódulos fixados. CMake/Ninja têm versões e hashes verificados.
Nenhuma dependência é instalada globalmente ou incorporada ao pacote principal.
Avisos upstream do libsrtp continuam visíveis; não são tratados como erros pelo
build GNU Windows. Código próprio permanece sujeito aos gates existentes.

`frontend/tests/native-encoder-streaming.mjs` é ensaio opt-in de texturas
sintéticas, negociação SDP em pipe pai/filho, H.264/RTP, DTLS-SRTP, SR e NACK,
sem STUN/TURN ou sala pública. HTTP do teste escuta somente loopback; o transporte
P2P ICE/DTLS-SRTP vincula uma interface IPv4 ativa específica, pois ICE exclui
candidatos loopback. Não abre servidor privilegiado nem muda firewall. SDP e
candidatos não são gravados no relatório. Perfil vem do SPS real e primeiro
quadro deve conter SPS/PPS/IDR. Há recuperação PLI/IDR no ensaio; faltam perdas
mais amplas, áudio sincronizado, múltiplos pares, reconexão e capturador real.
O protótipo não é seleção disponível na interface.

### Interoperabilidade observada

Ensaio nativo→Edge passou com120 quadros coloridos1280×720, alvo30FPS e entrada
medida≈30,01FPS, SPS42401f/resposta42e01f, dentro do nível negociado. Navegador
sem foco recebeu e decodificou120/120; callback de exibição contou5. Quatro
quadrantes RGB foram conferidos no próprio vídeo recebido, além do decoder MF.
Emulação de foco Playwright foi desativada e janela de teste minimizada. A API
ainda reportou visibilityState=visible/hasFocus=false; isso comprova sem foco,
não um documento que realmente reporta hidden. Timer privado de alta resolução
substituiu Sleep(1) no protótipo, sem busy spin ou alteração global do Windows.

Teste diagnóstico1080p120 também recebeu/decodificou120/120 e exibiu2 callbacks
sem foco. **O receptor anunciou nível3.1, abaixo do5.1 pedido pelo emissor.**
O ensaio antigo sem renegociação exige XENNEX_RTC_ALLOW_LEVEL_STRESS=1 e registra
withinNegotiatedLevel=false/diagnosticLevelStress=true. Não comprova negociação
válida de1080p120 nem autoriza selecionar esse perfil em produção. Gate padrão
do ensaio rejeita ultrapassar o nível anunciado. Derivar nível de dimensões/
macroblocos por segundo, não preservar o default inadequado do encoder.

O MFT local em Baseline66 produziu SPS42041f recusado pelo navegador; solicitar
ConstrainedBaseline256 gerou perfil aceito. A resposta DTLS padrão browser-active/
native-passive terminou com feature indisponível no MbedTLS; resposta passiva do
navegador, permitida na negociação, passou com verificação de certificado e SRTP.
**Atualização para MbedTLS3.6.7 resolveu o handshake padrão local.** Ambos os
papéis são testáveis, sem desligar criptografia ou fingerprint. Fragmentação era
hipótese compatível com correção upstream, não foi provada por captura de pacotes.
Fingerprint de resposta propositalmente incorreto gerou falha X509, peer failed e
zero mídia decodificada; baseline positiva passou com a mesma biblioteca.

### Validação atual de capacidade, ocultação e recuperação

XENNEX_RTC_NEGOTIATE_LEVEL=1 consulta MediaCapabilities para o perfil e dimensões
exatos, com prazo1,5s. Somente supported=true permite anunciar nível maior na
resposta; confirmação ocorre no fluxo realmente decodificado. No equipamento
local, supported/smooth/powerEfficient=true e SPS424033/resposta42e033 permitiram
1080p120 **dentro** do nível negociado. Não inferir isso para outros dispositivos.
Proveniência/commit/hash da DLL ficam no relatório; ensaio rejeita DLL stale.

Playwright noDefaults em perfil Edge descartável evita emulação de foco. O teste
oculto injeta apenas HTML sintético no documento inicial: navegar esse documento
reativou visibilidade emulada no harness, então não usar tal rodada como hidden.
Nenhuma API de visibilidade é sobrescrita. Teste720p30:54 quadros recebidos e
decodificados enquanto hidden/hasFocus=false, zero callbacks de exibição; após
restaurar, primeiro callback≈14,9ms. Teste1080p120 atual:240 codificados/enviados,
entrada≈120,01FPS,240 recebidos/224 decodificados ao final; fase realmente hidden
teve101 recebidos/99 decodificados e zero callbacks. Retomada≈18ms. Timeline
registra hidden→visible e permite usuário tirar foco novamente depois. Isso é
ensaio curto/sintético; não prova correção do caminho JPEG/canvas em produção.

PLI: primeiro IDR/SPS/PPS foi omitido intencionalmente no teste. Browser enviou
1PLI; ICodecAPI/VT_UI4 solicitou1keyframe e MFT produziu novo IDR (2 observados
incluindo o inicial omitido).119 enviados/118 recebidos e decodificados, cores
corretas. Pedidos coalescem e são limitados a um force/500ms no thread do encoder;
parâmetros SPS/PPS são repetidos em IDR quando faltam. Não é simulação de perda
UDP completa nem conclusão de NACK/backpressure/late join com vários espectadores.

Relatórios atuais em bin/streaming-qa/native-encoder-webrtc-1280-30-hidden-resume.json,
native-encoder-webrtc-1920-120-hidden-resume-capability.json e
native-encoder-webrtc-1280-30-pli-recovery.json. Na pasta frontend, executar
`node tests/native-encoder-streaming.mjs`; XENNEX_RTC_BACKGROUND=1 mede hidden e
retomada, XENNEX_RTC_PROFILE=1080p120 com XENNEX_RTC_NEGOTIATE_LEVEL=1 consulta e
negocia o nível; XENNEX_RTC_DROP_INITIAL_IDR=1 testa PLI e
XENNEX_RTC_TAMPER_FINGERPRINT=1 exige rejeição X509. Variantes são explícitas.
Dependências/licenças/proveniência, versões TLS suportadas e fallback precisam
do gate de distribuição antes de incorporar a biblioteca nativa ao pacote.

- [Perfis H.264 do Windows](https://learn.microsoft.com/en-us/windows/win32/api/codecapi/ne-codecapi-eavench264vprofile).
- [Negociação H.264/RTP](https://www.rfc-editor.org/rfc/rfc6184/).

## Referências primárias

### Captura WGC da própria janela

WgcProbeSource aceita somente fixture cujo PID, classe e executável correspondem
ao HWND fornecido pelo processo pai. Não contém fallback de monitor. Item e
ContentSize devem corresponder exatamente ao perfil1280×720; mudança encerra o
ensaio. FramePool2, aquisição limitada e timestamp SystemRelativeTime; frame e
referência de textura liberados após submissão da conversão. Sem staging/JPEG de
pixels no caminho novo; decoder CPU independente é somente verificação posterior.
120 quadros720p30 capturados, recebidos e decodificados; hidden real/retomada≈17,9ms
também passou. Fonte é janela sintética própria, não jogo nem tela pessoal.
Executar com XENNEX_RTC_WGC_FIXTURE=1 após build_native_webrtc.ps1 -BuildFixture;
XENNEX_RTC_BACKGROUND=1 acrescenta ocultação/retomada. A janela de cores aparece
temporariamente sem ativar jogos ou hooks. Teste continua fora do app distribuído.

### Controle de banda ainda em validação

Alvo MFT6Mbps não foi respeitado em120FPS:≈24Mbps inicialmente; nal12/filler
representou≈62% dos bytes. Ordem ICodecAPI antes dos tipos reduziu para≈10,7Mbps,
mas ainda não cumpre6. ModeCBR0, Mean6M e tipos120/1 foram lidos de volta;
LowLatency e bufferCBR187500bytes retornaramHRESULT0 sem corrigir a banda. Isso
não encerra E02/Q01. Não promover esse perfil como orçamento6Mbps garantido.

AMF direto está sendo comparado como backend opcional, SDK1.5.3 por commit fixado,
adaptador C próprio e runtime instalado carregado somente de System32. Nenhum
driver é copiado/instalado. Compilação passou; sessão C#/medição ainda pendentes.
Ausência/erro deve manter caminho compatível. Antes de distribuir, incluir licença
do SDK e validar bindings, cores, bitrate, latência, recursos e dispositivos reais.

Um ensaio alternativo de MediaStreamTrackGenerator versus canvas não conseguiu
estabelecer janela minimizada durante as duas publicações simultâneas (CDP
continuou normal/visible). Não foi considerado prova de ganho nem incorporado
ao caminho atual. Log experimental em bin/frame-source-background.log; nenhum
flag antithrottling foi ativado para mascarar a condição.

- [MFTEnum2](https://learn.microsoft.com/en-us/windows/win32/api/mfapi/nf-mfapi-mftenum2): enumeração de transforms por adaptador e liberação da lista.
- [MFT_ENUM_ADAPTER_LUID](https://learn.microsoft.com/en-us/windows/win32/medfound/mft-enum-adapter-luid): associação da consulta ao adaptador real.
- [Vortice.Windows](https://github.com/amerkoleci/Vortice.Windows): bindings já usados pelo capturador, versão3.8.3 fixada também no ensaio.

CodecQuery/CodecInfo WinRT servem como inventário, mas CodecInfo não oferece
IsAccelerated. Não usar esse inventário como comprovação de encoder GPU ou perfil.
