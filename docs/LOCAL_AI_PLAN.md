# IA local do Xennex

## Objetivo e decisões aceitas

Aba local de conversas, projetos e especialistas para a futura Alice. O usuário
quer executar tarefas cotidianas, código e processamento especializado no próprio
PC, sem serviço pago obrigatório. Hardware de referência: Ryzen 7 9800X3D,
32 GB RAM e RX 9060 XT com 16 GB VRAM. Este plano não altera a versão 0.2.3.

Especialistas consultam um catálogo de capacidades e podem solicitar ajuda entre
si. O coordenador mantém dependências, contratos, artefatos versionados, critérios
de conclusão, limites de rodadas e registro das decisões. Concordância entre
agentes não substitui testes nem medidas. Perfis podem compartilhar um modelo;
cadastrar um perfil não treina ou valida uma especialidade.

## Gerenciamento de recursos: a fila da impressora

Um serviço central é a autoridade de admissão. Agentes recebem uma fotografia de
consumo, reservas e fila e declaram sua demanda; não alocam recursos por conta
própria. RAM e VRAM são orçamentos diferentes. Capacidade de disco, CPU, GPU,
latência e energia precisam de políticas próprias nas etapas seguintes.

- Limite inicial: 75% da RAM e VRAM dedicadas totais, configurável de 50 a 85%.
- Consumo observado inclui outros programas. Reserva adicional por trabalho
  cobre carregamento ainda não realizado, contexto, buffers e saída; é estimativa,
  nunca uma garantia do driver. Modelo já residente não precisa ser contado duas
  vezes: sua memória já aparece na medição, mas o crescimento adicional precisa
  continuar reservado. Ollama agora tem estimativa por metadados e observações;
  motores compatíveis mantêm reservas manuais.
- Uma resposta por vez, FIFO, sem duas admissões concorrentes. Trabalhos que não
  cabem aguardam com motivo; o usuário pode cancelar ou mudar configurações quando
  a fila estiver vazia. Sem previsão de tempo inventada antes de haver amostras.
- Pressão durante execução cancela a solicitação, preserva a resposta parcial e
  pausa a fila. Retomada é explícita; não repete requisições automaticamente.
- Cancelar uma requisição HTTP não garante descarregar os pesos ou interromper
  imediatamente um servidor externo. Não encerrar processos de terceiros.
- Telemetria indisponível não equivale a zero. Em modo GPU, sem leitura válida de
  VRAM, a fila espera. No Ollama nativo, CPU envia num_gpu=0; na API compatível,
  configure também o motor externo para CPU.
- Um job divisível (vários arquivos, segmentos de áudio, etapas de código) pode
  usar checkpoints. Um modelo com necessidade mínima de 64 GB não vira um modelo
  de 8 GB só dividindo o pedido: requer modelo menor, quantização, offload viável
  ou outra máquina. Planejar particionamento por capacidade real da ferramenta.
- Margem de memória não limita utilização computacional a 75% e não impede um
  pico inesperado. Prioridade ao usuário é cooperativa, não reserva física do OS.

## Direção de arte e alternância com ComfyUI — plano aceito em 06/10/2026

O usuário aceitou alternar planejamento, geração e revisão visual, desde que a
troca evite acumular modelos e buffers em RAM/VRAM. Esta seção define trabalho
futuro; a integração ComfyUI e a entrada visual ainda não estão implementadas.
A fila de conversas existente não coordena hoje a execução externa do ComfyUI.

### Fluxo e autoridade de recursos

- Reutilizar a autoridade central de admissão para conversas, visão e ComfyUI;
  não criar uma segunda fila GPU independente que possa admitir trabalho junto.
  Executar uma etapa GPU por vez, inclusive durante cancelamento e limpeza.
- Sequência: planejar um trecho, salvar roteiro/referências, liberar a LLM,
  confirmar margem, gerar, salvar caminhos dos resultados, liberar os modelos
  de geração, confirmar margem e analisar as imagens. Revisão registra propostas
  de continuidade, sem substituir automaticamente fatos aprovados do personagem.
- Terminou a resposta não significa liberou memória. Confirmar fim da execução,
  solicitar descarregamento e combinar estado do motor com amostras recentes de
  RAM/VRAM antes de admitir a próxima etapa. HTTP 200, atraso fixo ou retorno ao
  consumo inicial isoladamente não provam que todas as alocações foram liberadas.
- Descarregamento lento, resposta perdida, motor ocupado, telemetria ausente ou
  memória acima do orçamento mantêm a troca em espera; após prazo limitado,
  pausar com motivo. Nunca tratar falha como zero consumo nem iniciar o próximo
  modelo para tentar recuperar. Cancelamento não libera a autoridade de recursos
  enquanto a etapa anterior ainda puder estar executando ou limpando.
- Modelo de residência deve ter endpoint, identidade do motor, modelo e dono do
  trabalho. Respostas tardias de uma execução cancelada não liberam nem avançam
  outra execução. Revalidar posse e cancelamento após cada operação assíncrona.

### Memória e isolamento

- Manter orçamento independente para RAM e VRAM, margem configurável e monitoramento
  de consumo global. Dimensionar reserva por modelo/workflow, contexto, resolução,
  batch e buffers; tamanho do arquivo de pesos não representa o pico da etapa.
- Começar com geração individual e poucos quadros por trecho planejado. Enviar
  imagens por caminho/identificador e carregar prévias limitadas quando necessárias;
  não manter todas as imagens completas/base64 e latentes do projeto em memória.
  Registrar picos observados sem reduzir reservas automaticamente por uma execução
  que consumiu pouco. Medir também o custo de recarregar os modelos.
- Offload pode reduzir VRAM e aumentar RAM. Modo CPU, quantização, resolução e batch
  são escolhas explícitas, sujeitas a medição; não migrar silenciosamente para CPU,
  RAM compartilhada ou arquivo de paginação para fazer uma etapa caber.
- Gerenciar inicialmente o Ollama iniciado pelo Xennex, conforme a política atual.
  Servidores externos e ComfyUI aberto pelo usuário precisam de concessão de controle
  definida para a sessão. Não encerrar processos de terceiros, limpar filas externas
  nem descarregar modelos de trabalhos alheios. Se há execução externa concorrente,
  aguardar; a leitura de memória não substitui o controle da sessão.
- Persistir roteiro, estado de continuidade e checkpoints em Data, não no KV cache.
  Reinício interrompe a produção e exige retomada explícita; não reenvia uma geração
  cujo resultado ainda não foi reconciliado com o histórico do ComfyUI.

### Primeiro recorte e critérios de aceite

Implementar primeiro os adaptadores de estado/liberação, a coordenação comum e
o indicador de etapa/espera/cancelamento. Depois conectar um workflow local já
validado e a análise visual. Sem download de pesos ou geração automática nesta
etapa de planejamento. O piloto usa um personagem e seis imagens, com revisão
individual quando a próxima cena depender do resultado anterior.

Testes determinísticos devem cobrir admissão concorrente entre chat e geração,
liberação demorada/recusada, resposta tardia, cancelamento durante troca, telemetria
ausente/desatualizada, pressão de RAM por offload, perda de conexão e reinício sem
duplicar geração. Um ensaio local autorizado mede vários ciclos com o workflow e
backend reais, registrando pico de RAM/VRAM, tempo e pausas. Aceite exige confirmar
que não se admite a etapa seguinte antes da barreira e que não há acúmulo progressivo
inexplicado; não exige retornar ao mesmo consumo byte a byte por causa de caches.
O limite é uma política de admissão, não um teto físico garantido pelo Windows/driver.

Referências técnicas: [descarregamento no Ollama](https://docs.ollama.com/faq) e
[rotas do ComfyUI, incluindo /free e /system_stats](https://docs.comfy.org/development/comfyui-server/comms_routes).

## Etapas

1. Base: contrato local de chat, histórico em Data/ai, cancelamento, fila,
   orçamento configurável, telemetria Windows e falhas visíveis.
2. Especialistas: cadastro de papéis, instruções, modelos e ferramentas; histórico
   de avaliações por capacidade e pedidos explícitos de ajuda.
3. Colaboração: tarefas e dependências persistentes, contratos frontend/backend,
   limites de tentativas, bloqueios, artefatos e checkpoints; uma escrita por
   arquivo por vez. Perfil simulado não deve aparecer como execução real.
4. Produção: ferramentas de arquivos/cálculos/testes, consultas aos dados do
   Xennex com fontes e permissões; dados externos são conteúdo, não instruções.
5. Áudio: medições, tratamentos específicos, comparação original/resultado;
   processamento ao vivo separado do modelo de conversa.
6. Expansão: arte, busca web, previsão baseada em medições, adaptadores para
   descarregamento de modelos e, só depois, datasets e treinamento avaliado.

## Recursos externos e pagos

O sistema pode sugerir uma ferramenta, especialista ou serviço externo quando
há uma lacuna demonstrável. Deve apresentar motivo, tentativas, alternativas,
dados enviados, estimativa disponível e teto de custo. Nenhuma sugestão autoriza
cobrança ou envio. A primeira etapa só aceita endereços HTTP em loopback, não
implementa fornecedores pagos, redirecionamentos nem downloads automáticos.
O motor configurado deve executar modelos locais: loopback sozinho não prova
que um proxy externo não encaminha conteúdo à nuvem.

## Implementação da primeira etapa

Serviços em src/Services/LocalAi, contratos em src/Models/LocalAi, interface em
frontend/src/features/local-ai. ApiBridge somente despacha. Cliente HTTP local
compatível com /v1/models e /v1/chat/completions, streaming SSE e timeout.
Histórico e configurações privados em Data/ai; nunca entram no pacote público.
Modelos e motores são dependências opcionais instaladas separadamente. A UI não
deve afirmar que existe modelo funcional sem uma execução real validada.

Validação: contratos HTTP com servidor/handler controlado, respostas progressivas,
falha/cancelamento, bloqueio de destinos externos, orçamento/telemetria ausente,
pressão durante execução, FIFO, persistência/reinício e interface responsiva.
Benchmark com modelo real depende de motor/modelo disponível e deve ser reportado
separadamente dos testes simulados. Nenhuma velocidade é prometida antecipadamente.

## Visão aprofundada em 19/09/2026: equipe que constrói entendimento

Origem: PDF de oito páginas, "conversa com o gemini sobre a questão que estamos
 desenvolvendo". O material contém uma conversa e referências a uma pesquisa,
mas não inclui o relatório completo da pesquisa. As falas do usuário esclarecem
objetivos; recomendações e comandos do Gemini são candidatos, não decisões
aprovadas nem autorização para instalação ou execução. Não assumir como fatos
os detalhes sobre a implementação da Alice mencionados apenas pelo Gemini.

### Colaboração e autonomia

- A equipe deve investigar o problema junto com o usuário antes de fixar o plano:
  especialistas levantam perguntas, possibilidades, limitações e divergências.
- O coordenador facilita a conversa, identifica participantes e acompanha o
  trabalho. Não substitui a competência de áudio, UI/UX, Windows, pesquisa etc.
- O usuário decide prioridades e aprova mudanças de escopo. Dúvidas rotineiras
  entre especialistas não devem exigir sua intervenção a cada mensagem.
- Cada especialista mantém identidade durável e uma interpretação revisável do
  projeto: objetivo entendido, hipóteses, dúvidas, informações necessárias,
  entregas propostas, destinatários, critérios de aceite e dependências.
- Essas interpretações são sínteses explícitas e verificáveis de trabalho;
  não exigem armazenar raciocínio interno do modelo. São atualizadas conforme
  chegam dados, feedback, decisões e resultados de ferramentas.
- Contratos de entrada/saída são negociados por tarefa. Um especialista em áudio
  não fica limitado permanentemente a entregar buffers: pode tratar voz, música,
  instrumentos, acústica ou dispositivos conforme sua capacidade avaliada.

### Memória, mensagens e decisões

Manter camadas distintas: registro completo da conversa para consulta/auditoria;
memória própria por especialista com fonte e data; decisões compartilhadas
aprovadas; interpretação atual de cada participante; e caixas de entrada/saída.
O registro comum de decisões pode conviver com atores e mensageria: não é preciso
abandonar consistência global para permitir interpretações diferentes.

Mensagens propostas: pergunta, proposta, pedido de insumo, entrega, revisão,
impedimento e mudança de decisão. Incluir projeto/tarefa, remetente/destinatário,
identificador, relação com solicitação anterior, versão de referência e links
para evidências/artefatos. Mensagens repetidas não podem executar a ação duas vezes.
Mudanças em decisões ou entregas invalidam dependências afetadas e notificam seus
consumidores; uma hipótese não se torna fato por ter sido repetida por outro agente.

Cada ativação recebe identidade, decisões relevantes, interpretação atual,
mensagens pendentes e evidências necessárias, com orçamento de contexto. Pode
solicitar detalhes/histórico quando o resumo for insuficiente. Evitar tanto copiar
a reunião inteira em toda chamada quanto esconder informação necessária em um
resumo excessivo. Um serviço de memória pode propor sínteses, preservar conflitos
 e relacionar versões; inicialmente isso não exige outro modelo sempre carregado.

### Separação dos controles

O mediador cuida da colaboração. O gerenciador central de recursos continua sendo
a autoridade de admissão: garante uma fila coerente e monitora o orçamento, mesmo
quando especialistas negociam horizontalmente. Uma resposta não dispara código
por conter um @nome ou um comando: pedidos de ferramenta passam por contratos,
validação, permissões e limites de execução. Serviços pagos continuam sujeitos à
aprovação explícita do usuário, com dados enviados, finalidade e orçamento.

### Cuidados técnicos com as sugestões do documento

Memória persistente, contexto enviado e KV cache são conceitos diferentes. Organizar
memórias e compor contexto seletivo não exige modificar ou treinar a rede neural.
Não pressupor que cache é descartado nem que VRAM é devolvida imediatamente após
cada chamada. O motor pode reutilizar cache e manter modelos residentes.

llama.cpp documenta opções independentes para tipos K/V e reutilização de cache:
https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
K em q8_0 e V em q4_0 é uma configuração candidata, não garantia de qualidade,
compatibilidade ou economia fixa. Avaliar com o modelo/backend concreto antes
 de adotar. Modelos grandes precisam ser medidos junto com pesos, contexto,
buffers e a margem do sistema; quantidade de parâmetros sozinha não basta.

CrewAI, AutoGen, ChatDev, Letta, Open WebUI, Open-LLM-VTuber e ferramentas de
fine-tuning citadas são referências para estudo, sem adoção automática. Voz,
avatar e treinamento de imagens são possibilidades levantadas na conversa;
prioridade continua sendo o escritório de especialistas integrado ao Xennex.

### Efeito na sequência de implementação

Preservar o chat e a fila já implementados. Próximos passos: melhorar o motor local
 e a medição de recursos, depois definir juntos os contratos de especialista,
interpretação, memória, entrega e mensagem. Uma primeira reunião deve permitir
perguntas e propostas antes da execução. Ferramentas reais, tarefas persistentes,
revisão e critérios de aceite vêm antes de autonomia extensa ou muitos agentes.
Esta atualização é de planejamento: não implementa especialistas nem troca o motor.

## Incremento implementado em 19/09/2026: motor e orçamento por modelo

A base de chat foi preservada. Ollama agora possui cliente nativo, detecção da
instalação/servidores, inicialização de processo próprio com nuvem desabilitada,
consulta de modelos residentes, contexto explícito, CPU e keep_alive. O processo
próprio encerra com o Xennex; liberar um modelo externo pelo app é recusado.

ModelMemoryEstimator distingue carregamento e residência confirmada no mesmo
contexto/modo. JobMemoryObservation registra deltas globais amostrados; perfis
persistidos só elevam reservas futuras. A fila consulta metadados antes de admitir
cada tarefa, revalida cancelamento depois da consulta e mantém monitoramento.
Configurações antigas continuam na API compatível com orçamento manual.

Validado com 60 checks, janela WebView2/COM nos dois protocolos e duas respostas
reais consecutivas de llama3:latest, reutilização de pesos e descarregamento.
Ainda faltam estimativas de tempo, disco/CPU/GPU computacional, partição de tarefas,
limpeza revisável de perfis de consumo e avaliação de capacidades de modelos.

Próximo incremento: contratos e interface de especialistas com identidade,
interpretação revisável e pedidos de ajuda. Depois, primeira reunião local com
perguntas/propostas e limites de rodadas, usando esta mesma fila; nenhuma resposta
de agente pode executar ferramentas sem a camada de contratos e permissões.

## Retomada acordada em 20/09/2026 (pendente; skins primeiro)

O usuário priorizou concluir o editor de skins. A implementação abaixo fica para
depois; não confundir este plano com capacidades já disponíveis no aplicativo.

- Salas/projetos com membros visíveis, identidade, papel e modelo de cada especialista;
  participação não significa manter seus pesos carregados. Reutilizar a fila serial.
- Plano geral editável por projeto, com histórico de decisões e revisões. Conversas
  simples continuam disponíveis sem cadastro obrigatório de projeto.
- Cadernos individuais persistentes em Markdown, editáveis, com origem, data e estado
  (proposta, hipótese, confirmada, superada). Preservar interpretações e divergências;
  consultar evidências originais quando houver conflito. Checkpoints incrementais.
- Contexto seletivo: plano atual, notas pertinentes, mensagens recentes e recuperação
  de trechos do histórico. Histórico em disco não equivale à janela de contexto.
- Pedidos de ajuda/convite entre especialistas, entregas e revisão com rodadas e
  orçamento limitados; interromper ciclos e nunca repetir tarefas após reiniciar.
- Ferramentas com contratos validados, concessões prévias por escopo ou aprovação
  de ações concretas. Texto e menções não executam comandos. Acesso pago requer
  aprovação explícita com finalidade, dados enviados e orçamento.
- Gerenciador determinístico de recursos como autoridade: medir consumo real,
  reservar margem configurável (75% por padrão), enfileirar e dividir trabalho.
  Não prometer limites físicos de RAM/VRAM que dependem do motor e do sistema.
- Comparar execução individual e equipe usando qualidade verificada, tempo,
  memória e intervenções. Especializar agentes não garante equivalência a um modelo
  maior; selecionar modelos e tamanhos de contexto com testes locais.
- Ferramentas de leitura/documentação primeiro, depois pesquisa e alterações de
  código revisáveis com testes. Áudio, imagem, treinamento e Alice são extensões
  posteriores, sem exigir outro modelo residente para cada papel.

Critério de aceite da próxima entrega: uma sala local utilizável, autoria clara,
plano e cadernos recuperados após reinício, reunião limitada usando a fila existente,
permissões verificáveis e comparação com uma execução individual. Preservar chats,
configurações e histórico atuais durante a migração.
## Incremento entregue em 20/09/2026: salas locais

Após concluir as skins, foi implementado o primeiro recorte utilizável do plano:
catálogo de especialistas com identidade/papel/modelo, salas com membros e
permissões de contexto, plano com revisões, cadernos individuais em Markdown,
propostas de memória revisáveis e reuniões de até três rodadas na fila serial.
Autoria, contexto selecionado, duração e deltas observados de memória ficam
registrados; avaliações humanas permitem comparar equipe e execução individual.

O esquema 2 preserva chats e configurações anteriores, com cópia original .v1.bak
antes da migração. Reiniciar não repete execuções. Cancelar ou falhar uma etapa
interrompe as etapas dependentes da mesma reunião. O guia de uso e os limites
estão em [LOCAL_AI_ROOMS.md](LOCAL_AI_ROOMS.md).

Cadernos são texto Markdown no armazenamento do aplicativo, com exportação;
não há sincronização automática de arquivos Markdown externos. Pedidos de ajuda
são conversacionais: o usuário ainda escolhe participantes e próximas rodadas.
A recuperação usa seleção limitada de notas e histórico; não há ferramenta
agêntica de busca ou de acesso a arquivos.

Próximos incrementos: contratos estruturados para pedidos de ajuda e entregas,
ferramentas de leitura com escopo e aprovação, recuperação explícita de evidências,
e só depois alterações de código revisáveis e execução controlada. Permanecem
futuros a previsão de duração, partição automática por recursos, pesquisa,
áudio/imagens, treinamento e integração com Alice. Acesso pago continua exigindo
aprovação explícita. Esta entrega não conclui toda a visão de agentes autônomos.

## Alice — laboratório de memória neural iniciado em 10/10/2026

O usuário autorizou começar a experimentar memória aprendida em pesos, com
associações entre imagem e áudio dentro de um sistema neural integrado. O
primeiro recorte está em [ALICE_NEURAL_MEMORY.md](ALICE_NEURAL_MEMORY.md): duas
redes perceptivas sintéticas alinhadas e congeladas, memória pequena treinada
apenas com imagens, consulta também por som, etapas de aprendizado, correção,
controles, checkpoint e medidas de esquecimento com/sem replay.

O laboratório Python é independente da aba e da fila, usa CPU e não baixa
modelos nem captura dispositivos. Não implementa uma LLM, um modelo omni, voz
ao vivo, autonomia ou memória das conversas pessoais. A ligação aos tensores
internos de um backbone real requer backend e interface treinada próprios.

Segundo recorte, tambem em 10/10/2026: `stream` aprende acontecimentos em ordem
por RLS, com pesos associativos e estado de covariancia, sem replay de episodios
anteriores. `stream-query` recupera interpretacao inicial/atual com contexto
fornecido. A correcao pai->mae preserva a impressao da refeicao e a atribuicao
inicial. Testes cobrem retencao, tres sementes, oracle de regressao em lote e
consulta em processo novo. Capacidade fixa, atributos supervisionados e contextos
separados por construcao; extracao autonoma de acontecimentos, plasticidade da
percepcao e integracao com raciocinio permanecem futuros.

Terceiro recorte em 10/10/2026: `time` treina uma GRU temporal pequena, com estado
persistente e decaimento dependente do intervalo. Sem indices de episodio, ela
antecipa sinais sinteticos usando ordem e duracao; controles removem continuidade
ou variacao dos intervalos. `time-query` retoma estado salvo e recebe somente o
sinal atual. Treino offline, pesos fixos na execucao e simulador de tempo;
isso nao conecta sensores/LLM nem demonstra experiencia subjetiva. Proximo
experimento: estado temporal formando chaves para a memoria de acontecimentos.

Quarto recorte em 10/10/2026: `context` une estado GRU continuo a um banco de
blocos RLS com enderecos latentes, sem numero de episodio na consulta. Importancia
duradoura, frescor do registro e reativacao de acesso sao separados; relevancia
limita a influencia da prioridade. Alocacao sob demanda ate uma capacidade,
varredura linear de enderecos e leitura de no maximo dois blocos. Dez novos
testes cobrem sementes, frio pertinente/quente irrelevante, lotacao e processo
novo. Enderecos/metadados sao explicitos e eventos/atributos/importancia ainda
sao fornecidos pelo simulador. Extracao autonoma de eventos, valor pessoal e
integracao com LLM permanecem futuros; o proximo recorte deve medir ambiguidades
e conflitos quando experiencias semelhantes carregam interpretacoes diferentes.

## Alice — plano de desenvolvimento em 10/10/2026

O plano completo está em [ALICE_DEVELOPMENT_PLAN.md](ALICE_DEVELOPMENT_PLAN.md):
ambiente sintético com percepção/ação/feedback, previsão latente, formação de
episódios e revisões, memória influenciando escolhas, valor aprendido, múltiplas
escalas temporais, consolidação, linguagem substituível e avaliação de Rust.
O primeiro lote recomendado é M0–M4. Na meta posterior, o usuário autorizou avanço
no plano completo e escolheu iniciar com linguagem pré-treinada, avaliando padrões
herdados antes de decidir se ensinar do zero. A implementação atual já testa ciclo
causal, previsão contrastiva/recorrente e uma ponte textual com Gemma local. Os
resultados e falhas reais ficam no laboratório; episódios gerais, consolidação,
valor aprendido e integração persistente continuam parte da meta ativa.

O avanço seguinte acrescentou cenas/sons compostos, descoberta de acontecimentos
em fluxo único, memória RLS com interpretação inicial/atual e correções dirigidas
por pistas e tempo. Uma política pequena já muda escolhas conforme essas
lembranças, com controles e retomada em outro processo. São recortes supervisionados
de um mundo sintético; ainda não estão integrados ao runtime contínuo do Xennex,
ao preditor de 16 dimensões ou à linguagem natural. A meta completa permanece ativa.

O laboratório agora acopla esses episódios a pendências, evocação interna e valor
aprendido de consequências externas. Três fluxos reservados de 10 mil passos
preservaram datas, recuperaram a lembrança útil e mantiveram filas limitadas; a
preferência muda se as consequências mudam. Worker real finito com um thread
consumiu ~1,77% de um núcleo e ~190 MB no ensaio de 30 s em repouso. A ponte textual
pode ler esses checkpoints, mantendo confiança factual separada de importância.
Não há ainda supervisor permanente/fontes reais no Xennex; escalas aprendidas,
consolidação e influência longitudinal da LLM continuam no escopo completo.
