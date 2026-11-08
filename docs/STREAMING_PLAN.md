# Plano de evolução do streaming — Xennex Live

Atualizado em **04/11/2026**. Escopo: salas, compartilhamento, áudio, visualização,
compatibilidade e funções de convivência discutidas para o grupo. Este é o backlog
consolidado do streaming; biblioteca de artes, VR, ComfyUI e Alice mantêm seus
planos próprios. Planejamento não significa que os itens abaixo foram implementados.

### Ordem vigente — estrutura e integração do conjunto (04/11/2026)

O usuário manteve o objetivo integral, mas mudou a execução: construir a estrutura
completa e conectar os fluxos básicos antes de aprofundar testes de uso, otimização
local e acabamento. A [arquitetura de implementação](STREAMING_ARCHITECTURE.md)
mapeia as 48 tarefas, contratos, dependências e donos dos recursos.

Trabalhar em rodadas horizontais: não ficar em um componente até deixá-lo pronto.
Registrar limitações e continuar integrações independentes; parte da solução pode
estar em outro módulo ainda não construído. Compilação, segurança, ciclo de vida
e testes determinísticos acompanham as mudanças; benchmarks repetidos e polimento
voltam depois do conjunto funcional. Os critérios de aceitação abaixo continuam
valendo para declarar entrega, mas não exigem encerrar uma frente para iniciar outra.
Nenhum item foi removido ou marcado concluído por essa mudança de ordem.

### Execução em andamento — 03/11/2026

O objetivo completo continua ativo. Primeiro lote implementado:

- **R01, parcial:** diagnóstico estruturado da entrada, tentativa/build, etapas,
  classificação de timeout e relatório sem identidades/SDP/credenciais. Falta
  reproduzir o caso do amigo na ponta afetada; não declarar sua causa resolvida.
- **R02, parcial:** falha síncrona ao criar Peer/coordenador/canal não deixa a UI
  ocupada indefinidamente. Demais ensaios físicos do ciclo continuam pendentes.
- **R03, parcial:** medição voluntária RTP de 60/900 s com distribuições e relatório
  local. Teste real sintético de 60 s, dois vídeos 800×450/30, cerca de 28,9/29,4
  FPS médios. Não mede captura bruta, CPU/GPU ou latência sincronizada; baseline
  nativa e matriz física seguem necessárias.
- **E01/E02, protótipo parcial:** inventário MF/DXGI por adaptador, perfil H.264
  real, conversão GPU por quadro em pool limitado e decoder independente. Teste
  sintético1920×1080/120 mediu entrada≈120,15FPS e validou120 quadros coloridos.
  Ainda não integrado à captura real nem ao app; limites em NATIVE_ENCODER.md.
- **E03, protótipo parcial:** H.264 nativo/RTP/DTLS-SRTP→Edge com120/120 quadros
  recebidos/decodificados em720p, alvo30FPS, entrada≈30,01FPS, dentro do nível
  negociado. Consulta específica do decoder permitiu1080p120 negociado no PC
  local:240 recebidos/224 decodificados, retomada≈18ms após hidden real. TLS3.6.7
  resolveu handshake padrão; fingerprint inválido rejeitado. Recuperação de IDR
  omitido via PLI passou. Áudio, perdas/carga amplas, múltiplos pares e capturador
  real seguem pendentes; produto atual conserva o caminho JPEG/canvas.
- **U01, implementado:** grade, livre, foco com miniaturas, encaixe opcional na
  grade, salvar organização local e restaurar padrão. Slots anônimos seguem a
  ordem de exibição, não a identidade das pessoas. Validação de reload/móvel e
  áudio contínuo; refinamento com o grupo permanece aberto.
- **D01, entregue neste lote:** pacote oficial assinado/root atualizados e site
  publicado com protocolo v3/TURN desligado. Identificação e evidências no contexto
  do agente. A tarefa reaplica-se aos próximos lotes que precisarem de entrega.

Lembrete do usuário incorporado: medir sem foco, aba oculta e minimização. RTP
agora separa chegada de quadros (framesReceived) de encode/decode; relatório
registra contagem de amostras focadas/sem foco/ocultas. A integração headless
observou documento visível/focado; não é prova de aba realmente oculta. Testes
unitários cobrem chegada60/decode5 e gaps/reset. Experimentos com Edge minimizado
também reportaram visible, portanto validação física de ocultação continua aberta.
Remover flags antithrottling do teste evita mascarar o comportamento, mas não
substitui a confirmação de document.visibilityState/hasFocus em cada cenário.
No protótipo RTC novo, perfil Edge descartável/noDefaults e documento sintético
inicial produziram hidden real. Entrada/chegada continuaram enquanto a exibição
parou; retorno à visibilidade foi registrado em timeline. Evidências detalhadas
em NATIVE_ENCODER.md; não confundir com teste do capturador JPEG atual.

Ensaio nativo isolado visível/focado teve chegada aproximada28/35/49FPS para
alvos30/60/120 em800×600, com captura processada≈30/41/54FPS. Passou no gate
funcional; não atende a meta de95% dos alvos mais altos. Não concluir que lag em
segundo plano ou desempenho nativo foram resolvidos. E01–E03 e R03 seguem necessários.

As outras frentes conservam o escopo integral abaixo. Este registro não encerra
itens que dependem de teste externo nem converte pesquisa em implementação.

## 1. Direção do produto

O site no Cloudflare é a experiência principal dos amigos. O app Windows oferece
captura e áudio adicionais, sem se tornar requisito para assistir. Preservar arte,
skins e identidade visual do Xennex, com controles familiares de chamada.

- P2P como padrão; recursos novos sem assinatura obrigatória ou API paga.
- Automático deve usar capacidades verificadas e medidas locais. Fabricante,
  idade ou preço da GPU não determinam suporte; quem recebe também precisa ser avaliado.
- Opções avançadas só aparecem como disponíveis quando o caminho estiver implementado.
  Ausência de uma API deve permitir alternativa compatível e explicar a limitação.
- Alvo escolhido, quadros capturados, codificados, recebidos e exibidos são medidas
  diferentes. Não prometer 1080p/120 em qualquer equipamento ou conexão.
- Nunca trocar silenciosamente uma janela por um monitor inteiro. Captura de jogo
  com hook continua explícita; não alterar jogo, driver ou anticheat automaticamente.
- Avisos de nova transmissão são visuais e silenciosos, conforme pedido do grupo.
- TURN permanece **desligado**. Publicar o Worker não ativa o serviço; eventual
  ativação depende de necessidade demonstrada e controle de consumo acordado.

## 2. O que já existe e o que ainda não foi comprovado

Inventário conferido nos componentes de streaming, Worker, testes e registros do
projeto. Testes locais/sintéticos não substituem ensaios sustentados nos amigos.

| Frente | Estado atual | Limite ou pendência real |
| --- | --- | --- |
| Salas | PeerJS + WebRTC, protocolo v3, presença, eleição e recuperação do coordenador testadas. | Falha persistente do amigo ao entrar ainda sem diagnóstico da ponta afetada; causa não confirmada. |
| Distribuição web | Worker com Static Assets publicado via Wrangler; interface compartilhada com o app. | Hospedagem da página não hospeda a sinalização PeerJS nem fornece relay automaticamente. |
| Múltiplas fontes | Telas, abas/janelas do navegador e câmera; assinaturas e volumes independentes. | Limites lógicos de 32 participantes, 6 fontes locais e 32 assistidas não são garantia de desempenho nessa carga. |
| Inicialização | Progresso, cancelamento, prazos, limpeza de captura atrasada e erro de áudio separado do vídeo. | Repetir ciclos no uso real, incluindo fullscreen, troca de fonte e dispositivos removidos. |
| Captura Windows | WGC de janela/monitor, DXGI de monitor, recuperação e redimensionamento GPU antes do readback. | Caminho ainda passa por RAM, JPEG, WebSocket local, decode/canvas e novo encode WebRTC. |
| Captura de jogo | Hook OpenGL próprio x86/x64 experimental; osu! fullscreen chegou a aproximadamente 30/60/120 FPS na captura bruta. | Não é suporte genérico a Direct3D/Vulkan nem prova de entrega 1080p/120 ao espectador. Módulo fica residente desativado até o jogo terminar. |
| Medição | FPS RTP/exibição distintos, codec real, bitrate, perdas, RTT, recuperação e tempos por etapa quando disponíveis. | Faltam baseline sustentado entre redes, orçamento total de CPU/GPU/RAM/VRAM e comparação antes/depois por dispositivo. |
| Codecs | Auto, compatibilidade e preferência H.264/VP8/VP9/AV1; decisão independente de envio/recepção, sem remover alternativas. | MediaCapabilities fornece estimativas; placas físicas antigas e de outros fabricantes não foram validadas. Encoder nativo direto ainda não existe. |
| Apresentação | Grade, palco livre, foco com miniaturas, oito bordas/cantos, teclado, duplo clique para foco e ferramentas em Somente telas; salvar/restaurar organização local. | Um layout local por slots anônimos; faltam múltiplos perfis e refinamento com o grupo. |
| Aviso de tela nova | Nome iluminado, Assistir com degradê/selo Nova e contador; sem som/autoplay; movimento reduzido respeitado. | Acompanhar legibilidade e percepção no uso real. Não reimplementar como item pendente. |
| Áudio | Sistema/aba conforme navegador; no app, processo selecionado e filhos, separado da fonte de vídeo. | Microfone anexado à câmera não equivale a chamada de voz independente. Browser puro não oferece nossa captura seletiva por processo Windows. |
| TURN | Broker e opção individual implementados e testados sem serviço real; renovação manual prevista. | Sem ativação, credenciais reais ou teste de relay. Recuperar só uma mídia em sessão ativa é etapa adicional. |
| Entrega Windows | Pacote assinado da etapa do hook existe; frontend local e site receberam codecs e aviso visual depois. | Reempacotar o ZIP oficial para incluir esses incrementos de interface; bundle local atualizado não significa ZIP atualizado. |
| Funções sociais | Câmera e consumo simultâneo de transmissões existem. | Voz independente, chat, mídia sincronizada e ferramentas colaborativas continuam no backlog. |

Os registros antigos em [STREAMING_REVIEW.md](STREAMING_REVIEW.md) e
[STREAMING.md](STREAMING.md) descrevem o estado de cada data. Por exemplo, os
1–2 FPS do DXGI no osu! não invalidam o teste posterior do hook OpenGL; são
caminhos diferentes. Usar o inventário acima para decidir trabalho novo.

## 3. Como executar o plano

**P0**: confiabilidade e entrega. **P1**: próximo investimento de desempenho e
compatibilidade. **P2**: evolução da experiência e novas funções. **P3**: pesquisa
condicionada a evidência. A prioridade é relativa, sem prazo fictício.

Cada ID é uma tarefa rastreável. Dividir itens grandes em lotes com contrato,
teste, resultado e fallback antes de iniciar a próxima integração. Marcar como
concluído apenas com evidência e registrar o incremento em AGENT_CONTEXT.md.

### Etapa A — estabilizar e medir a experiência atual

| ID / prioridade | Trabalho restante e alcance | Critério de conclusão |
| --- | --- | --- |
| R01 · P0 | **Diagnosticar quem não entra**: distinguir sinalização PeerJS, identificação/protocolo da sala, conexão de dados, ICE/DTLS e mídia. Web + app. | Diagnóstico curto copiável sem IP/SDP/segredos, erro por etapa e teste na ponta afetada. Não atribuir automaticamente a browser ou TURN; mesmo browser admite configurações diferentes. |
| R02 · P0 | **Ciclos de captura reais**: iniciar/cancelar/parar/reiniciar, fonte encerrada, seletor negado, janela minimizada, fullscreen/Alt+Tab, troca de resolução e áudio removido. | Sem loading infinito, captura órfã ou congelamento silencioso. Ação de recuperação e fonte selecionada preservadas; sem vazamento entre donos/sessões. |
| R03 · P0 | **Benchmark reproduzível por etapa**: cenas sintéticas de texto, movimento e quadro estático; medição em emissor e receptor. | Registrar alvo e resultado, dimensões, codec, FPS, tempos p50/p95, descartes, uso de recursos e condição de rede. Separar captura bruta de entrega completa. |
| R04 · P0 | **Compatibilidade física no grupo**: AMD/NVIDIA/Intel, integrada/dedicada, antiga/recente, navegadores e duas redes reais. | Matriz com aprovado, degradado ou indisponível, evidência e fallback. Simulação VP8-only continua regressão, não substituto de hardware real. |
| R05 · P1 | **Recuperação isolada**: falha de uma fonte/assinatura não deve reiniciar as demais; testar longa duração, sleep/wake e queda do coordenador sob carga. | Recuperação limitada/cancelável, áudio dos outros mantido e memória sem crescimento contínuo após sucessivos ciclos. |
| R06 · P1 | **Alternativa TURN por necessidade**: concluir teste real da base existente e, depois, desenhar retry só da conexão afetada durante sessão ativa. | P2P permanece padrão; rota efetiva identificada; desligamento/expiração testados; consentimento e limite de consumo definidos antes de ativar. Não oferecer como correção de falha de sinalização. |

R01 pode avançar com testes simulados e UX de diagnóstico; sua causa específica
fica aberta até haver evidência do amigo. R03 é pré-requisito para alegar ganho
de desempenho. R06 não precisa bloquear os caminhos diretos que já funcionam.

### Etapa B — reduzir o custo da captura nativa

Objetivo: evitar a etapa JPEG e o segundo encode **no caminho nativo novo**,
mantendo o espectador no navegador e o caminho atual como alternativa.

| ID / prioridade | Trabalho restante e dependência | Critério de conclusão |
| --- | --- | --- |
| E01 · P1 | **Probe de encoders por adaptador**: consultar capacidade real de resolução/FPS/codec/formato; avaliar Media Foundation, AMF, NVENC e Intel como candidatos. Depende de R03. | Resultado disponível/indisponível/desconhecido por caminho, motivo de falha e teste sintético. Sem carregar tudo ao iniciar a sala ou mudar driver; nenhuma marca ganha suporte por suposição. |
| E02 · P1 | **Protótipo isolado GPU → H.264**: textura D3D11, conversão BGRA → NV12 e encoder de baixa latência. Selecionar primeiro backend pela interoperabilidade e medidas. | Cores/proporção corretas, recursos limitados, parada limpa, qualidade e custo comparados ao caminho atual. Demonstrar quais cópias foram removidas; não chamar de zero-copy sem verificar. |
| E03 · P1 | **Entrega nativa para WebRTC de navegador**: especificar SDP/ICE, packetização RTP, timestamps, áudio sincronizado, RTCP, perdas e late join. Depende de E02. | App transmite e amigo assiste pelo site, sem plugin. Cliente antigo continua no caminho compatível; falha não derruba a sala nem muda a fonte. Prova antes de trocar a implementação padrão. |
| E04 · P1 | **Seleção automática e fallback de backend**: custo, disponibilidade e ensaio curto orientam recomendação; escolha manual permanece. Depende de E01–E03 e R04. | Recomendações explicáveis; falha de encoder oferece caminho atual. Não reinjetar hook nem iniciar outra captura silenciosamente. Limitar sessões de hardware e memória ao publicar várias fontes. |
| E05 · P2 | **OpenGL e fullscreen**: otimizar a ponte GPU do hook separadamente; tratar contexto destruído, avisos de reinício e ciclo de vida. | Repetir fixtures x86/x64 e teste autorizado do jogo; preservar estado GL. Nenhuma promessa de compartilhamento de textura entre APIs/adaptadores antes do teste. |
| E06 · P2 | **Mais capturas nativas e APIs de jogo**: projetar sessões independentes; avaliar Direct3D/Vulkan apenas se jogos do grupo exigirem. | Contrato por fonte, limites de GPU/IPC, cancelamento e áudio sem cruzamento. Novos hooks são opt-in e podem ficar indisponíveis em jogos protegidos. |

AMF é um candidato de interop multimídia, não uma solução para todos os
fabricantes. Uma pilha como libdatachannel é candidata ao transporte WebRTC
nativo, não fornece sozinha captura/encoder nem integração pronta com o nosso
PeerJS. Comparar bibliotecas, licenças, manutenção e reprodução de falhas antes
de escolher dependência. [AMF oficial](https://github.com/GPUOpen-LibrariesAndSDKs/AMF),
[libdatachannel oficial](https://github.com/paullouisageneau/libdatachannel).

### Etapa C — qualidade adequada a cada pessoa

| ID / prioridade | Trabalho restante e alcance | Critério de conclusão |
| --- | --- | --- |
| Q01 · P1 | **Auto por medidas sustentadas**: aproveitar a seleção de codecs existente e adicionar orçamento/carga observados, com histerese e intervalo mínimo entre mudanças. Web + app. | Não oscilar perfis continuamente; explicar gargalo e recomendação. Modo manual preserva intenção e avisa quando alvo não chega, sem inventar FPS. |
| Q02 · P1 | **Qualidade por espectador**: estudar perfis de envio, prioridade do vídeo em foco e capacidade de decode de cada ponta. Depende de R03/R04. | Receptor fraco assiste sem impor seu limite a todos; upload total, encodes e memória continuam limitados. Validar simulcast/SVC ou perfis separados antes de expor opções. |
| Q03 · P2 | **Texto, jogo e vídeo**: presets explícitos, codec negociado, nitidez versus fluidez e consumo; perfis 720p/1080p/1440p e FPS suportados. | Comparações reproduzíveis de texto e movimento; sem ampliar fonte menor nem vender 120 FPS medidos só na captura. 4K é ensaio condicionado ao equipamento. |
| Q04 · P2 | **Regiões alteradas e cursor**: avaliar API disponível no Windows, composição DXGI e cursor separado opcional. Depende de E02/E03 para otimizações de encode. | Tela estática continua correta; cursor visível, sem duplicação, bem mapeado em DPI/rotação/recorte. Fallback de quadro completo para clientes/Windows sem suporte. |
| Q05 · P2 | **Recepção econômica**: limitar trabalho de vídeos ocultos e priorizar foco, preservando os áudios escolhidos. | Ganho medido com várias telas e abas em segundo plano; retomar sem tela preta ou perda de áudio. Diferenciar pausar decode, reduzir envio e apenas esconder CSS. |

Em mesh, mais espectadores significam mais cópias/upload; encoder GPU não elimina
isso. Um mesmo bitstream pode ser reutilizável sob condições compatíveis, mas
perfis diferentes podem exigir novos encodes. O limite de qualidade deve refletir
esse orçamento, não apenas a opção selecionada no formulário.

### Etapa D — controles de áudio e chamada

| ID / prioridade | Trabalho restante e alcance | Critério de conclusão |
| --- | --- | --- |
| A01 · P2 | **Voz independente**: microfone sem câmera, mute/deafen, volume, seleção de entrada e estado por pessoa. Web + app. | Voz e áudio de transmissão têm controles separados; sem criar microfone automaticamente. Reconexão não muda mute nem duplica áudio. |
| A02 · P2 | **Supressão, eco e atalhos**: controles de processamento de voz, teste de microfone e push-to-talk. Depende de A01. | Processamento de voz não destrói o som do jogo; atalhos locais web e globais nativos distinguíveis, sem prometer tecla global no browser. |
| A03 · P2 | **Saída e mixagem**: dispositivo de saída quando a API permitir, volume mestre e acesso claro aos volumes existentes por transmissão. | Falha de permissão/dispositivo tem fallback; deafen restaura escolhas anteriores; sem som duplicado ao mudar foco. |
| A04 · P2 | **Áudio de processo**: refinar UX nativa de incluir/excluir processo e filhos; avaliar auxiliar opcional para quem usa o site somente se houver necessidade. | Exclusão/inclusão medida em processos sintéticos. Nada apresentado como disponível antes de implementar; site continua funcional sem auxiliar e sem contornar permissões do navegador. |

### Etapa E — apresentação da sala

| ID / prioridade | Trabalho restante e alcance | Critério de conclusão |
| --- | --- | --- |
| U01 · P2 | **Layouts persistentes e presets**: grade, foco com miniaturas, livre, encaixe/alinhamento e reset; salvar preferências locais. | Restaurar em outra resolução sem deixar telas fora do palco, adaptar à mudança de participantes e manter controles acessíveis. Não confundir com divisão de painéis da galeria. |
| U02 · P2 | **Entrada e compartilhamento guiados**: recomendações curtas de fonte/áudio/qualidade, progresso por etapa, estados de carregamento e recuperação claros. | Usuário entende o que vai compartilhar, o que está iniciando e o motivo da limitação sem ler detalhes de engenharia. Preservar modal e opções avançadas atuais. |
| U03 · P2 | **Acessibilidade e consistência visual**: teclado, toque, foco, contraste sobre skins, movimento reduzido e telas estreitas. | Assistir/Parar/Transmitir utilizáveis com zoom e teclado; nomes/novos avisos legíveis. Avisos permanecem silenciosos e não abrem vídeo automaticamente. |
| U04 · P2 | **Indicador de saúde simples**: resumo da qualidade e dica acionável, com diagnóstico técnico expandível. | Distinguir problema de captura, encode, rede e recepção quando medido; sem culpado inventado nem 0 FPS para dado ausente. |

### Etapa F — funções inspiradas nas referências

Backlog funcional das conversas e prints, **sem planos Pro, anúncios, moedas,
badges pagos ou assinatura**. Cada módulo precisa de contrato antes de execução;
a tabela não presume que todo detalhe das referências foi escolhido pelo usuário.

| ID / prioridade | Função proposta | Dependências e critério de conclusão |
| --- | --- | --- |
| C01 · P2 | **Chat e reações**: texto, histórico da sessão e reações opcionais. | Limites de payload/frequência, conteúdo escapado, reconexão e migração; não executar HTML enviado por outro participante. Definir retenção local antes de persistir. |
| C02 · P2 | **Permissões da sala**: definir papéis, quem controla mídia/ferramentas, aprovação/remoção e convites privados. | Identidade e autorização reais, não confiar só em nome/flag enviada pelo cliente. Definir eleição dos papéis sem promover qualquer visitante por acidente. Código da sala não equivale a autenticação forte. |
| C03 · P2 | **Assistir juntos**: player sincronizado, fila/playlist, pausa/busca e controle pelo dono ou grupo. | Começar com um provedor permitido por embed, depois avaliar YouTube/Twitch/Kick separadamente. Respeitar APIs, autoplay, diferenças de disponibilidade e drift; não capturar credenciais nem prometer suporte universal. |
| C04 · P2 | **Fonte de vídeo local**: arquivo escolhido pelo usuário e controles compartilhados. | Definir transmissão versus transferência e orçamento de rede, sincronizar áudio/vídeo e limpar recursos ao parar. Arquivo local não vira URL acessível aos outros sozinho. |
| C05 · P2 | **Notas e tarefas compartilhadas**. | Primeiro modelo de operações/versionamento, limites e exportação; concorrência, duplicação e entrada tardia testadas, com permissões C02. |
| C06 · P2 | **Lousa e anotações sobre tela**. | Coordenadas independentes da resolução/crop, limites de traços e limpeza, rejoin e permissão; anotação não interfere no clique/captura da pessoa. |
| C07 · P2 | **Editor de código compartilhado**. | Reutilizar sincronização das notas; texto colaborativo sem execução remota por padrão. Linguagens/realce, tamanho e persistência definidos. |
| C08 · P2 | **Arquivos P2P**. | Consentimento para enviar/receber, tamanho/progresso/cancelamento, hash, chunks com backpressure e caminho seguro; sem executar arquivo recebido nem sufocar mídia. |
| C09 · P2 | **Gravação e clipes locais**. | Indicador explícito de gravação, escolha de fontes/áudio, armazenamento/quotas e exportação. Medir custo e informar participantes; não iniciar silenciosamente. |
| C10 · P3 | **Legendas, transcrição e tradução opcionais**. | Avaliar modelos locais e rotação de CPU/GPU/RAM sem competir sem limite com transmissão. Privacidade/retenção e consentimento definidos; sem API paga obrigatória. |
| C11 · P2 | **Temas da sala e perfis leves**. | Aproveitar skins/tokens existentes; preferência visual pessoal separada do tema compartilhado, imagens limitadas e fallback de acessibilidade. Sem sistema de loja/monetização. |

Ordem sugerida desta etapa: C01/C02, depois C05 e C03; lousa, arquivos e gravação
vêm em lotes próprios. A01 pode ser priorizado antes se o grupo quiser substituir
também a chamada de voz, em vez de continuar com voz no Discord.

### Etapa G — ideias avançadas: investigar antes de integrar

| ID / prioridade | Ideia recebida | Porta de entrada / condição para avançar |
| --- | --- | --- |
| X01 · P3 | ROI / mapas QP, AV1 com ferramentas de tela, intra-refresh e slices. | Depois de E02/E03: suporte consultado por codec/driver, benefício medido, late join/PLI/perdas corretos. Não assumir 80% dos bytes no cursor, metade do bitrate ou ausência total de keyframes. |
| X02 · P3 | 4:4:4, HEVC, HDR/P010. | Encoder, transporte, decoder e apresentação precisam aceitar o perfil. Validar cores/range/tone mapping; SDR/H.264/VP8 continuam alternativas. Não basta a GPU aceitar textura RGB. |
| X03 · P3 | Fences e filas GPU; apresentação nativa com swapchain de baixa latência. | Profiling deve identificar espera evitável. Visualizador DirectX é opção do app; não melhora automaticamente o elemento video de quem usa o site. |
| X04 · P3 | Sharpen/upscale no receptor. | Opt-in com comparação visual e custo local. Filtro espacial não recupera texto perdido; não presumir dados temporais/profundidade do jogo para DirectSR/FSR. |
| X05 · P3 | MoQ/LOC, WebTransport, Iroh/Quinn, SRT/RIST e L4S. | Protótipo separado somente se rede/latência justificar, com web, NAT, criptografia e custo documentados. WebTransport é cliente-servidor; não trocar P2P por servidor sem decisão explícita. |
| X06 · P3 | FEC customizada, RaptorQ e reconstrução/PLC. | Comparar com proteções WebRTC existentes e medir perda, redundância, tempo e artefatos. Concealment estima imagem; não equivale a recuperar bytes originais. |
| X07 · P3 | SFU / encaminhamento central. | Somente se upload/escala exigirem e houver plano de hospedagem/consumo aceito. Diferenciar servidor de sinalização, TURN e SFU; manter opção direta. |

WebTransport não é um substituto direto do WebRTC P2P no navegador, conforme
[explainer do W3C](https://github.com/w3c/webtransport/blob/main/explainer.md).
TURN retransmite tráfego e envolve consumo: franquia não é teto financeiro nem
garantia de custo zero. Ver [FAQ oficial Cloudflare](https://developers.cloudflare.com/realtime/turn/faq/)
e nosso [contrato de TURN](STREAMING_TURN.md). As demais referências técnicas e
correções às alegações do Gemini estão em [STREAMING_REVIEW.md](STREAMING_REVIEW.md).

### Etapa H — entrega, segurança e manutenção contínuas

| ID / prioridade | Trabalho restante | Critério de conclusão |
| --- | --- | --- |
| D01 · P0 | **Alinhar pacote Windows e site**: incluir os últimos incrementos no pacote oficial, identificar build em diagnóstico e manter rollback. | Build app/web, pacote assinado pelo script oficial, hashes/versões conferidos e smoke app→site; protocolo compatível ou migração explícita. Preservar Data/ e skins. |
| D02 · P1 | **Regressões e CI úteis**: manter testes determinísticos de sala/captura, ampliar casos somente quando novo risco justificar; browser real como integração separada. | CI já existe: conferir resultado remoto após commit/push autorizado. Testes GPU/hook/monitor continuam opt-in, sem câmera/tela pessoal no CI. Não declarar validação remota com resultado só local. |
| D03 · P1 | **Observabilidade mínima e segura**: correlação de tentativa/versão, métricas limitadas e relatório voluntário; atualizar registros antigos com links para estado atual. | Sem tokens, credenciais TURN, SDP/IPs, nomes de janela, chat ou imagens nos logs compartilhados. Logs do Worker cobrem suas invocações, não o tráfego P2P inteiro. |
| D04 · P1 | **Revisão de fronteiras ao ampliar funções**: validação de mensagens/limites, origem/token de IPC, binários assinados e dependências/licenças. | Cliente hostil não ganha comandos do Windows nem autoridade de sala. Manter pinning, limites de filas e cancelamento; registrar política de atualização/rotação de chave quando alterada. |
| D05 · P1 | **Separar entregas no Git**: revisar diffs e organizar lotes de streaming sem misturar alterações de Alice/galeria/outros módulos. | Commits e publicação somente no escopo autorizado; nenhum reset ou descarte da árvore atual para facilitar o trabalho. Dependências de release documentadas. |

## 4. Próxima rodada de construção

Seguir o mapa de [STREAMING_ARCHITECTURE.md](STREAMING_ARCHITECTURE.md), sem
retomar o ciclo de otimizar cada protótipo até o alvo antes de integrar os demais.

1. Consolidar fronteiras de sessão, captura/saída, transporte, qualidade, áudio e
   operações compartilhadas; preservar o caminho atual como adaptador compatível.
2. Conectar o fluxo básico entre essas frentes, incluindo os pontos de entrada de
   voz e ferramentas. Definir negociação/versionamento antes de ligar recursos
   novos aos peers. Funcionalidades ausentes continuam explicitamente pendentes.
3. Migrar partes reutilizáveis dos protótipos nativos para módulos de produção
   somente com ownership, cancelamento e contrato de transporte definidos; não
   depender de executáveis de teste nem exigir JPEG perfeito antes dessa integração.
4. Implementar capacidades em rodadas do conjunto: mídia, áudio e operações de
   sala evoluem sem monopolizar o trabalho em uma única frente. Anotar pendências
   locais e revisar ao completar o fluxo relacionado.
5. Verificar compilação, contratos e falhas entre módulos. Depois retomar matriz
   física, desempenho/foco/fullscreen, refinamentos de UX e entrega versionada.

O amigo com falha de entrada e equipamentos indisponíveis continuam como validação
externa pendente. TURN permanece desligado. Novas opções só se tornam padrão após
validação; estrutura desenhada e testes determinísticos não comprovam desempenho
nem compatibilidade física. Não publicar funcionalidades vazias ou instáveis.

## 5. Matriz de aceitação e evidências

| Dimensão | Cobertura a registrar |
| --- | --- |
| Emissor/receptor | Browser→browser, app→browser, browser→app; preferência de codec diferente em cada ponta; cliente anterior compatível. |
| Hardware | AMD/NVIDIA/Intel disponíveis, integrada/dedicada e híbrida, memória limitada e encoder ocupado por outro programa. Identificar limites, não presumir suporte. |
| Navegadores | Edge/Chrome/Brave/Firefox; Safari e Android/iOS quando disponíveis. Registrar assistir, compartilhar e capturar áudio separadamente. |
| Fonte | Texto fino/colorido, jogo em movimento, cena estática, câmera; janela fechada/minimizada, monitor secundário, DPI/rotação e fullscreen/Alt+Tab. |
| Rede | Mesma LAN e redes distintas, IPv4/IPv6 quando disponíveis, perda/jitter/banda restrita e firewall. Relay só quando ativação estiver acordada. |
| Carga | Começar 1 fonte/1 receptor; depois 2/4/8 receptores quando viável e várias fontes. Não confundir participantes conectados com vídeos realmente assistidos. |
| Ciclo | Entrada tardia, host sair/cair, reconectar, mudar codec, cancelar seletor, expirar acesso alternativo e sair com transmissão ativa. |
| Interface | Desktop/móvel, zoom, teclado, foco, reduced-motion, skin clara/escura, Somente telas e retorno ao app/compacto. |

Registrar por execução: build, plataforma/capacidades relevantes, fonte e perfil,
rota direta/relay, duração/amostras, FPS por etapa, bitrate, RTT/perdas/freezes,
CPU/GPU/RAM/VRAM disponíveis, resultado esperado/observado e limitações da medição.
Latência ponta a ponta precisa de ensaio próprio; subtrair relógios não
sincronizados ou somar tempos médios de APIs não comprova esse valor.

Para cenas com movimento gerado, usar como **meta de avaliação**, não garantia de
produto, média de pelo menos 95% do FPS alvo nos dispositivos/perfis aprovados.
Caso falhe, identificar a etapa, medir frame pacing e documentar um perfil menor
estável. Em cena estática, FPS menor pode ser esperado: verificar frescor/correção
da imagem, não fabricar quadros para satisfazer o contador. Recursos devem atingir
platô e retornar após ciclos; entrada/cancelamento respeitam os prazos definidos
nos respectivos contratos, sem espera indefinida.

### Gate de cada entrega

- Atualizar o contrato da área e o estado dos IDs afetados antes de declarar pronto.
- Executar `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_ci.ps1`.
- Para frontend: `npm test`, `npm run lint`, `npm run build` e `npm run build:web`;
  integração UI/WebRTC correspondente quando comportamento mudar.
- Para nativo: build e fixtures do caminho alterado; captura real/hook apenas com
  autorização aplicável, sem imagens pessoais salvas por padrão.
- Publicar web/pacote em entrega própria com versão e rollback; teste local não
  significa que os amigos já receberam. Atualizar AGENT_CONTEXT.md com evidências.

## 6. Documentos e pontos de implementação

| Área | Referência |
| --- | --- |
| Estado de salas, captura, UX e métricas | [STREAMING.md](STREAMING.md); `frontend/src/features/stream/` |
| Codecs, estimativas e fallback do navegador | [STREAMING_CAPABILITIES.md](STREAMING_CAPABILITIES.md) |
| Hook, ciclo de vida, assinatura e resultados reais | [GAME_CAPTURE.md](GAME_CAPTURE.md); `src/CaptureWorker/` |
| TURN individual e limites de ativação | [STREAMING_TURN.md](STREAMING_TURN.md); `cloudflare_pages/worker.mjs` |
| Revisão histórica e propostas do Gemini | [STREAMING_REVIEW.md](STREAMING_REVIEW.md) |
| Hospedagem, deploy e reversão | [README Cloudflare](../cloudflare_pages/README.md) |
| Regressões, segurança e empacotamento | [TESTING.md](TESTING.md), [SECURITY_REVIEW.md](SECURITY_REVIEW.md), `.agents/rules/release-packaging.md` |

Ao retomar em outro chat/modelo: ler este plano, STREAMING.md e as regras da área;
ler também STREAMING_ARCHITECTURE.md e conferir o código atual antes de editar.
Avançar a integração do conjunto em incrementos verificáveis, sem concentrar
novamente todo o trabalho em aperfeiçoar um único componente. Não transformar
hipótese de pesquisa, contrato ou protótipo em alegação de recurso entregue.
