# Revisão do streaming — 06/10/2026

Plano atual consolidado em [STREAMING_PLAN.md](STREAMING_PLAN.md), atualizado em
02/11/2026. As prioridades e descrições abaixo são registros das respectivas
datas; consultar o inventário do plano antes de considerar uma correção pendente.

Avaliação atual das sugestões de arquitetura enviadas pelo usuário em 01/11/2026:
ver a seção [Avaliação das sugestões de pipeline](#avaliação-das-sugestões-de-pipeline--01112026).

**Registro histórico anterior às correções.** A implementação posterior de
inicialização cancelável/assíncrona, fidelidade e interrupção do áudio,
diagnóstico RTP e validação ICE está descrita em
[STREAMING.md](STREAMING.md#correções-de-inicialização-e-áudio-06102026).
Os limites arquiteturais e testes entre redes continuam aplicáveis.

## Resultado e escopo

A base de salas e transmissão passou nos testes existentes e nas integrações
executadas nesta revisão. Não foi reproduzida falha de criação/entrada, troca
de coordenação ou início de vídeo nativo nas condições testadas. Há um problema
reproduzido de perda silenciosa do áudio local e pontos confirmados no código
que precisam ser corrigidos antes de ampliar as funcionalidades.

Esta etapa é uma auditoria. Não altera captura, protocolo, áudio ou interface,
não atualiza o executável e não publica no Cloudflare. Os builds web foram
regenerados pelos comandos oficiais para testar o código atual. Dados pessoais,
modelos e skins não foram usados como mídia de teste.

## Arquitetura e funções existentes

- `StreamWorkspace.tsx` compartilha a interface entre app, popout e navegador.
- `RoomClient.ts` gerencia mídia, assinaturas, reconexão e eleição;
  `RoomCoordinator.ts` distribui presença e solicitações de assinatura.
- Cada espectador escolhe as fontes que recebe. Há áudio e volume por fonte,
  múltiplas fontes assistidas, destaque, grade, posição livre e redimensionamento.
- A coordenação migra entre participantes. O coordenador não distribui vídeo;
  as conexões entre sobreviventes podem continuar durante a eleição.
- Os limites são 32 participantes, seis publicações por pessoa e 32 fontes
  assistidas por pessoa. São limites de admissão, não garantias de desempenho.
- O app separa a janela de vídeo do processo de áudio. A seleção por PID captura
  processo/árvore de processos, não necessariamente uma aba ou janela exclusiva.
- Resolução, FPS de 0 a 120, prioridade de detalhe/movimento e orçamento de upload
  já existem. Zero é automático, não captura parada.
- A sinalização padrão usa o serviço público PeerJS. A mídia usa WebRTC direto;
  o Cloudflare hospeda a página e não funciona como retransmissor de vídeo.

## Problemas confirmados e prioridades

### P1 — desconexão do áudio não é comunicada

`frontend/src/features/stream/capture.ts:144` instala apenas `onmessage` no
socket de áudio. `openCaptureSocket` remove seus handlers de abertura/erro/fechamento
ao entregar o socket aberto. O vídeo tem tratamento de fechamento, mas o áudio
não tem equivalente. Após a interrupção, a faixa produzida pelo AudioContext
continua ativa e o usuário não recebe indicação de perda de som.

Reprodução isolada: `node bin/streaming-review/audio-disconnect.mjs` transpila os
módulos atuais e usa vídeo, áudio, ponte e sockets sintéticos. O fechamento do
socket de áudio manteve a faixa `live`, o aviso vazio e não chamou o callback
de encerramento. Parada explícita ainda liberou os recursos. O fixture fica em
`bin/`, ignorado pelo Git; esta reprodução ainda não integra a suíte permanente.

Correção proposta: estado de áudio separado do estado de vídeo, aviso de
interrupção e recuperação limitada/cancelável ou opção de continuar sem áudio.
Evitar anunciar uma transmissão com som quando o transporte local caiu.

### P1 — início/parada do áudio pode bloquear a interface

`src/Services/ProcessAudioCaptureService.cs:410` espera o início com
`WaitOne(4000)`; a parada usa `Join(1000)` na linha 647. A ponte chama esses
métodos diretamente. Quando executados na thread da interface, podem causar
travamento perceptível. O limite de quatro segundos não inclui necessariamente
todo o tempo de parada e limpeza.

Correção proposta: início/parada assíncronos com timeout, cancelamento e estado
explícito. Manter a inicialização COM/WASAPI na thread apropriada e impedir que
um worker antigo interfira em uma captura nova. Não simplesmente envolver todo
o serviço em `Task.Run` sem revisar as transições e a propriedade dos recursos.

### P1 — ganho fixo altera e pode distorcer o áudio

`src/Services/ProcessAudioCaptureService.cs:672` multiplica amostras estéreo
float32 por 1,5 e limita o resultado a -1/+1. Uma amostra 0,8 passa a 1,0,
em vez de manter sua amplitude; picos acima de aproximadamente 0,667 saturam.
O comportamento depende do formato/caminho de conversão, pois outros ramos não
aplicam esse mesmo ganho. É um problema confirmado pela transformação no código;
não foi feita avaliação auditiva do áudio pessoal nesta revisão.

Correção proposta: ganho padrão unitário e controle explícito, com teste de
amostras e de conversão. Se houver amplificação opcional, informar saturação e
avaliar um limitador apropriado sem adicionar latência desnecessária.

### P2 — diagnóstico não contabiliza todo o tráfego

`RoomDiagnostics.tsx:22` soma apenas RTP de vídeo. Os valores não representam
áudio, retransmissões e todos os overheads da conexão. `quality.ts` também apenas
registra no console a falha de aplicação de parâmetros do encoder.

Correção proposta: distinguir vídeo, áudio e tráfego total estimado; exibir
qualidade solicitada, efetivamente recebida e ajustes que não foram aplicados.
Informar limitações de rede/processamento sem prometer entrega garantida.

### P2 — configuração e manutenção dos testes

`peerConfig.ts` valida superficialmente `urls` de servidores ICE e calcula
`HAS_TURN` por presença de texto na configuração, independentemente de o JSON
ter sido aceito. Uma configuração inválida pode produzir indicação enganosa.
Nenhum `.env` ativo foi encontrado em `frontend/`; só `.env.example`, portanto
os builds executados usaram STUN padrão e nenhum TURN configurado.

`scripts/tests/test_stream_native.ps1` ainda tem pacote 0.2.3 como padrão. A
revisão passou explicitamente o diretório 0.2.4. Corrigir esse padrão/resolução
de pacote e incluir regressões para áudio interrompido, conversão de amplitude
e cancelamento durante inicialização.

## Limites da arquitetura

### Upload e qualidade

O remetente cria uma conexão para cada combinação de publicação e espectador.
`RoomClient.ts:214` utiliza o menor orçamento de upload configurado nas fontes e
divide o orçamento entre todas as conexões de saída. `quality.ts:20` reserva
15% do upload informado e calcula o teto por conexão.

Exemplo com uma tela 1080p60, upload informado de 12 Mbps e espectadores
assistindo essa tela:

| Espectadores | Teto de vídeo por conexão |
| --- | --- |
| 1 | 10,2 Mbps |
| 2 | 5,1 Mbps |
| 8 | 1,275 Mbps |

São tetos calculados, não medições da internet nem bitrate efetivamente usado.
O preset 1080p60 permite até 16 Mbps, mas o orçamento pode limitar abaixo disso.
Preservar resolução solicita `maintain-resolution` e escala 1; não cria banda,
capacidade de codificação ou detalhe visual. O resultado pode manter dimensões
com pior compressão ou menos quadros. Conteúdo complexo exige mais que o vídeo
sintético deste teste.

Melhoria proposta: validar orçamento antes de iniciar, informar entrega real e
permitir prioridades por fonte/espectador. Para grupos grandes, estudar SFU
opcional em máquina/servidor disponível. Software livre não elimina necessidade
de hardware, banda, energia e disponibilidade; não impor serviço pago.

### Captura nativa e custo de processamento

`CaptureSessionService` e `NativeCaptureService` mantêm uma sessão nativa global
por instância, com um worker e portas fixas. O limite de seis publicações não
equivale a seis capturas WGC nativas independentes: fontes adicionais precisam
usar outros caminhos, como captura do navegador ou câmera.

O caminho nativo é WGC → readback da GPU → JPEG de qualidade 88 → socket local
→ decodificação em canvas → codificação WebRTC. Há compressão intermediária e
trabalho de CPU/memória. É candidato a otimização para alta resolução/FPS, mas
não foi medido nesta revisão a ponto de atribuir um gargalo concreto a ele.
O smoke nativo foi em 800×600, não 4K120.

### Redes, versões e acesso às salas

Sem TURN, certas combinações de NAT/firewall podem estabelecer presença e falhar
na mídia. TURN e SFU cumprem funções diferentes; adicionar um não resolve
automaticamente todas as limitações do outro. A eleição também depende da
disponibilidade da sinalização PeerJS.

O manifesto público `https://xennex-live.alexdoong11.workers.dev/xennex-stream.json`
respondeu HTTP 200 com `protocol: xennex-room-v3` e `series: 0.2`, iguais ao
manifesto gerado. Isso confirma identificação compatível, não que todos os
arquivos publicados sejam idênticos ao build local ou que app/site entre redes
diferentes já tenham sido testados nesta rodada.

A sala usa conhecimento do código como mecanismo de entrada. Não há senha,
convite autenticado, aprovação de entrada ou moderação completa. Códigos curtos
escolhidos manualmente são mais fáceis de adivinhar. A validação do protocolo e
das fontes existe, assim como proteção do transporte local por origem/token.

## Evidências de validação

| Verificação | Resultado e limite |
| --- | --- |
| `npm test` | Passou: salas simuladas, reconexão, migração, 32 participantes, seis fontes, assinaturas, separação HWND/PID, cancelamento e parâmetros de qualidade. |
| `npm run build` e `npm run build:web` | Passaram. Bundle local gerado, sem deploy. |
| `dotnet build Xennex.csproj -c Release` | Passou, zero avisos/erros. |
| `scripts/tests/test_ci.ps1` | Passou: segurança, skins, jogos, biblioteca, VR, IA, compacto, gestos, release e updates. Exceções sintéticas esperadas fazem parte dos testes negativos. |
| `browser-stream-quality.mjs` | WebRTC real local: envio e recebimento 1920×1080 a 60 FPS; sem limitação reportada; mídia sintética, upload configurado 30 Mbps, um receptor. |
| `browser-streaming.mjs` | PeerJS e WebRTC reais no Edge, três transmissores, duas telas mais câmera, áudio simultâneo, seleção, layouts, entrada tardia, saída e queda abrupta do coordenador. Sem exceções de página. |
| `test_stream_native.ps1 -BuildDirectory 'Backup/Xennex-v0.2.4-win64'` | Três ciclos em cópia limpa/WebView2: primeiro frame em 2769, 264 e 251 ms, 800×600; tentativa única, token inválido rejeitado e navegação externa bloqueada. Só a própria janela de teste. |
| Fixture de interrupção de áudio | Falha reproduzida: fechamento não gera aviso/recuperação; limpeza explícita passa. |

A mensagem PeerJS de peer inexistente no teste de navegador é esperada: o teste
primeiro tenta entrar em uma sala que ainda não foi criada. Não é falha da suíte.

Ainda faltam ensaios entre PCs/redes diferentes, escuta de áudio real de dois
processos, isolamento de eco, qualidade com movimento/jogo, capturas 1080p60 e
120 FPS pelo worker nativo, muitas fontes/espectadores reais, minimização,
suspensão e perda/restauração de conectividade. Simular 32 participantes não
equivale a validar 32 computadores transmitindo.

## Sequência proposta para evolução

1. Corrigir confiabilidade e fidelidade de áudio; tornar inicialização/parada
   assíncronas e ampliar as regressões específicas. Validar novamente app/browser.
2. Tornar qualidade e consumo visíveis, incluindo limites de upload, estado de
   áudio e configuração ICE aceita. Testar carga representativa do grupo.
3. Projetar múltiplas sessões nativas e avaliar otimização de transporte de
   frames com medições antes de trocar codecs/arquitetura.
4. Adicionar voz independente e chat, com mute/deafen, dispositivos e permissões
   compartilhadas entre app e navegador. Microfone anexado à câmera não é uma
   chamada de voz independente.
5. Adicionar mídia sincronizada e ferramentas compartilhadas em incrementos:
   notas/tarefas, depois lousa/anotações e demais funções das referências.
6. Avaliar SFU/TURN próprios como opções para redes/grupos que precisem, mantendo
   o caminho direto e sem exigir assinatura de terceiros.

O plano detalhado das novas funções deve partir desta revisão. Não incluir
monetização, anúncios ou serviços pagos obrigatórios. Gravação, transcrição,
tradução, arquivos, temas e perfis precisam de contratos próprios de privacidade,
armazenamento e recursos; não tratá-los como pequenos botões sem implementação.


## Avaliação das sugestões de pipeline — 01/11/2026

Os textos do Gemini foram recebidos como referências para análise, não como
instruções para trocar automaticamente a arquitetura. Comparação com o código:

| Camada | Xennex nesta revisão | Avaliação / próximo passo |
| --- | --- | --- |
| Captura | Navegador, WGC e novo monitor DXGI | DXGI não existia no pacote de 31/10. Recuperar troca de modo é prioridade para osu!; não exige trocar transporte. |
| Memória | Nativo: textura → staging CPU → JPEG → socket → bitmap/canvas → encoder WebRTC | Não é zero-copy. O readback/JPEG é nosso, não uma obrigação universal do WebRTC. O caminho navegador + áudio nativo evita essa conversão própria, sem provar zero-copy interno do browser. |
| Codec | Negociação pelo WebRTC do navegador/WebView2 | Não temos controle próprio AMF/NVENC/VPL, QP maps, perfis 4:4:4, slices ou intra-refresh. Confirmar capacidades de emissão e recepção antes de escolher codec. |
| Rede | PeerJS + WebRTC, mesh P2P; alternativa TURN ainda desligada | Mais espectadores multiplicam cópias/upload. Trocar captura não resolve ICE/NAT. Nenhuma assinatura/serviço pago foi ativado. |
| Cursor / regiões alteradas | WGC compõe cursor; DXGI ainda não compõe cursor separado. Não enviamos cursor ou dirty rects ao encoder | A premissa “vocês já mandam cursor separado e usam regiões no encoder” não corresponde ao código. |
| Receptor | Elemento video no browser/WebView2 | Não temos decoder/swapchain DirectX próprios, super-resolução ou PLC neural configurável. |

### O que as propostas permitem concluir

- **ROI / mapas QP:** a extensão existe e influencia quantização por blocos.
  “80% do bitrate no cursor” é uma política/estimativa a desenvolver, não uma
  garantia de divisão dos bytes. Exige suporte real de encoder/driver e não se
  conecta simplesmente ao nosso RTCPeerConnection. [Khronos](https://www.khronos.org/blog/khronos-announces-vulkan-video-encode-av1-encode-quantization-map-extensions).
- **4:4:4 em toda GPU recente:** não confirmado; para RX 906x a própria tabela
  AMD indica VCN 5.0 e codecs 4:2:0. Aceitar textura RGB não prova bitstream 4:4:4.
  Não assumir suporte AV1/HEVC 4:4:4 ou custo de latência zero em todos os fabricantes.
  [AMD](https://github.com/GPUOpen-LibrariesAndSDKs/AMF/wiki/GPU-and-APU-HW-Features-and-Support).
- **DirectSR/FSR:** algoritmos temporais costumam precisar de profundidade,
  vetores de movimento e outros dados de renderização que a imagem capturada não
  fornece. Um filtro espacial CAS/sharpening é outra opção, mas não recupera texto
  ou detalhe perdido, nem garante metade da banda ou decode abaixo de 1 ms.
  [Microsoft DirectSR](https://microsoft.github.io/DirectX-Specs/DirectSR/DirectSR.html).
- **Filas/fences D3D12:** GPU-side Wait/Signal é um mecanismo real, não uma
  novidade exclusiva de 2026. O custo evitável depende de medição; não há ganho
  universal de 0,5–2 ms por quadro. [ID3D12CommandQueue::Wait](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12commandqueue-wait).
- **MoQ/moq-lite/LOC:** existem trabalhos e implementações; distinguir drafts
  do grupo e propostas de implementação. Não é substituição direta de P2P WebRTC.
  WebTransport do navegador é cliente-servidor. QUIC não elimina RTT, filas,
  controle de congestionamento ou necessidade de algum buffer; tampouco remove
  os casos em que hole punching falha e um relay é necessário.
  [IETF MoQ](https://datatracker.ietf.org/group/moq/documents/),
  [moq-lite](https://datatracker.ietf.org/doc/draft-lcurley-moq-lite/),
  [W3C WebTransport](https://www.w3.org/TR/webtransport/).
- **FEC/PLC:** RaptorQ já foi padronizado em 2011. FEC precisa de redundância;
  overhead não é universalmente 20–30%. Concealment estima uma imagem, enquanto
  FEC recupera dados quando há informação suficiente. Os textos fornecidos não
  identificam uma implementação ou benchmark reproduzível que entregue os números
  “neural/smart FEC” propostos para este app. [RFC 6330](https://www.rfc-editor.org/info/rfc6330/).
- **Sub-frame, AV1 e intra-refresh:** dependem do codec, perfil, implementação,
  GPU, decoder e padrão de perdas. Não assumir que habilitar AV1 elimina keyframes,
  reduz sempre o bitrate pela metade ou garante latência menor. Essas opções
  precisam ser negociadas e avaliadas com entrada tardia e recuperação de perdas.

### Ordem de evolução recomendada — ainda não implementada

1. Concluir a compatibilidade/recriação DXGI, validar no osu! real e manter os
   testes de captura restrita, áudio, salas e seleção de monitor.
2. Medir por etapa: frames da fonte, idade da imagem, readback, JPEG, decode/canvas,
   encoder, perdas/RTT e p50/p95. “qualityLimitationReason=none” não prova que o
   capturador anterior ao encoder está entregando o alvo.
3. Prototipar separadamente captura D3D11 → conversão GPU NV12 → encoder de hardware
   de baixa latência. Começar por interoperabilidade com receptores existentes;
   não substituir as salas. Entregar bytes codificados ao PeerJS/WebRTC atual
   exige integração própria, não apenas importar um SDK.
4. Negociar codecs/capacidades por receptor e avaliar texto, movimento, HDR e
   consumo reais. Depois considerar ROI e filtros opcionais, com fallback.
5. Rever SFU/QUIC somente se métricas de escala/rede justificarem, preservando
   suporte ao navegador e preferência por P2P. Não prometer relay sem consumo.

Não foi implementado encoder nativo, MoQ, 4:4:4, super-resolução, controle remoto,
FEC customizada ou reconstrução neural nesta correção de fullscreen.


### Incrementos validados após a revisão (01/11/2026)

Readback reduzido por shader GPU, telemetria por etapa, decode VideoFrame com
fallback e fila de último JPEG pendente foram implementados. RTP agora distingue
codec, tempos de encode/decode, buffer, perdas e NACK/PLI quando disponíveis.
Detalhes e números em STREAMING.md. Os itens3–5 da evolução (encoder nativo,
negociação avançada/ROI/4:4:4, SFU/QUIC) continuam futuros; essas mudanças não os
implementam indiretamente.

O osu! real revelou ACCESS_LOST em sequência no fullscreen; o teste sintético não
cobria a apresentação OpenGL do jogo. Janela/sem bordas chegou a≈30/59/120FPS no
socket local. Adicionado guard de instabilidade, aviso e encerramento limitado;
não declarar fullscreen real corrigido nem atribuir a baixa taxa à rede sem esses
contadores. Relato comparável: https://github.com/obsproject/obs-studio/issues/14021.
