# Modelos locais e continuidade da conversa

## Modelos preparados em 20/09/2026

| Modelo | Pesos em disco | Uso inicial |
| --- | --- | --- |
| qwen3.5:4b | 3,16 GiB | Conversa e planejamento; comparar com Gemma na Nissi |
| qwen2.5-coder:7b | 4,36 GiB | Geração e revisão de trechos de código |
| gemma3:4b | 3,11 GiB | Alternativa para conversa e comparação |
| llama3:latest / llava:latest | Já existentes | Preservados para comparação |

Tamanhos medidos no catálogo instalado, sem contexto e buffers. Instalar não
carrega todos na RAM/VRAM; a fila continua serial. A consulta no app mostra os
modelos instalados, não certifica sua competência. Os testes usam 75% de orçamento,
contexto 4096 e saída 256; configurações pessoais não foram alteradas.

Para usar: iniciar Ollama pelo Xennex, abrir Especialistas, Atualizar modelos
instalados e escolher o modelo no perfil. Modelo vazio continua usando a escolha
global. Para Nissi, experimentar gemma3:4b e qwen3.5:4b; manter a mesma pergunta ao comparar.

## Armazenamento e instalação explícita

Os modelos desta máquina foram preparados em Data/ai/models, no E:. A instância
própria detecta esse diretório quando ele contém manifests e mostra o caminho na
interface. Sem esse diretório, preserva o padrão/OLLAMA_MODELS herdado do Ollama.
Não altera variáveis de usuário nem servidores externos. Modelos antigos foram
copiados, com originais preservados no C:. Modelos e conversas não entram no Git
nem no pacote público.

O script scripts/setup_ai_models.ps1 baixa os três modelos acima somente quando
executado explicitamente. Requer Ollama, porta 11437 livre e 40 GiB de margem em
disco. Preserva o catálogo original e verifica os downloads via Ollama. A interface
não inicia downloads e não conecta serviços pagos.

Bonsai 4B Q2_0_g64 foi baixado do repositório oficial e testado com Ollama 0.33.3:
a consulta de metadados falhou com HTTP 500, tensor token_embd.weight size overflow.
Seu manifesto foi arquivado em Data/ai/model-imports; o blob verificado permanece
no armazenamento. Não está no catálogo ativo. Integrá-lo exige validar um motor
compatível antes de oferecer seleção. Mistral permanece alternativa do plano;
não foi baixado por sobrepor o papel de conversa já coberto nesta rodada.

Modelos de áudio, geração de imagem e ferramentas de pesquisa exigem adaptadores
próprios. A entrada atual é texto, mesmo quando os pesos admitem visão. O Bonsai
também não substituirá validação determinística de JSON ou admissão de memória.

## Correção do caso Nissi

Antes, mensagens eram enviadas em ordem inversa, todas como usuário. Uma resposta
longa podia ser omitida enquanto sua pergunta antiga era mantida, estimulando
novas apresentações e respostas a assuntos passados.

AiHistoryWindow seleciona trocas completas por recência. AiRoomContext envia a
seleção em ordem cronológica, preserva assistant para a própria especialista e
identifica contribuições de colegas. Tentativas falhas não voltam como perguntas
sem resposta. Quando a troca mais recente excede o orçamento, usa trechos literais
sinalizados, com IDs no relatório; o histórico integral continua em disco. Não é
um resumo semântico nem contagem exata de tokens.

O perfil pede continuidade e informa a existência de notas revisadas. Não afirma
acesso ao computador ou a conteúdo de caderno que não foi incluído. No Ollama,
think=false evita que modelos híbridos gastem a saída em raciocínio separado sem
entregar texto; controle configurável desse modo fica para outra etapa.

## Aprender pela conversa

Em Cadernos, Orientar aprendizado permite indicar preferências, correções ou
entendimento do projeto. Propor memória produz uma nota candidata; revisar e
confirmar antes de reutilizar. Isso adapta o contexto persistente, não os pesos.
Notas ruins podem ser corrigidas ou marcadas como superadas. O modelo ainda pode
errar e deve distinguir suas interpretações do que o usuário explicitamente disse.

## Evidências e fontes

104 verificações automatizadas cobrem a infraestrutura e a regressão de contexto.
O teste WebView2/COM cobre salas, cadernos e reinício. O roteiro --conversation-real
avalia apresentação, caderno vazio, resposta direta e recuperação de preferências;
a etapa final desativa histórico para testar a nota isoladamente. Artefatos ficam
em bin/AiConversationReal-*; falhas de qualidade permanecem registradas.

Resultados observados (amostra curta, não benchmark): Gemma recuperou as duas
preferências somente pela nota revisada. Qwen respondeu diretamente e recuperou
parte da preferência no teste isolado; em outro teste com histórico disponível,
recuperou ambas. Coder gerou a função C# de paridade correta, mas falhou no critério
de recuperação e incluiu uma atribuição incorreta na nota candidata. Llama passou
pela sequência sem refazer a apresentação nas perguntas seguintes, mas sua nota
foi pouco útil. Não aprovar automaticamente essas propostas nem atribuir competência
apenas pelo nome do modelo.

Fontes oficiais consultadas:
- [Qwen 3.5](https://ollama.com/library/qwen3.5:4b)
- [Qwen Coder](https://ollama.com/library/qwen2.5-coder:7b)
- [Gemma 3](https://ollama.com/library/gemma3:4b)
- [Thinking no Ollama](https://docs.ollama.com/capabilities/thinking)
- [Bonsai: formatos e motores](https://github.com/PrismML-Eng/Bonsai-demo)
