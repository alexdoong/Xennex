# Alice — episódios integrados e evocação contextual

Direção discutida com o usuário em01/11/2026. Documento de implementação em
aberto; os requisitos abaixo não são capacidades já demonstradas.

## Detalhe visual como pista de um momento — 08/11/2026

O fluxo local aceita até quatro recortes por imagem. Usa o encoder visual instalado
para representar a cena e cada recorte separadamente. Os recortes ficam ligados
ao mesmo momento e ao SHA-256 da imagem, com suas coordenadas na origem. A cena
continua no banco associativo junto ao som e a outras modalidades atendidas.
Se a atenção descartar a imagem, os recortes não entram na memória.

Com evocação implícita habilitada, um recorte da entrada atual pode selecionar um
momento anterior. O banco lê esse momento a partir da chave visual aprendida na
aquisição e recupera suas representações disponíveis, como o som da ocasião. A
semelhança mínima de 0,90 e a margem de 0,04 para o segundo momento são heurísticas
iniciais. O caminho regional se abstém em caso de empate próximo ou baixa
similaridade. Nesses casos, a evocação da cena continua com seu critério próprio.
O recorte oferece uma pista perceptiva e nenhuma afirmação sobre identidade física.

As coordenadas podem ser manuais ou vir do JSON local do Mirage. A importação usa
apenas caixas de objetos e a ordem pelo escore de detecção. IDs, nomes sugeridos,
OCR e relações ficam fora da memória desse ensaio. O Mirage é uma fonte opcional de
propostas. O vetor visual continua sendo produzido pelo encoder da Alice.
[Referência do formato do Mirage](https://cactuscompute.com/blog/structured-perception)

Cada vetor ocupa 512 bytes em float32. O teto de quatro por momento e 2.048
momentos representa 4 MiB de vetores, além das caixas, hashes e estruturas.
Recortes saem com a aposentadoria do momento. A tabela de endereços fica no
checkpoint, junto aos endereços de cenas. Os fatores do episódio continuam
paginados e a seleção regional lê no máximo um episódio. Checkpoints legados
abrem sem inferir detalhes que nunca foram adquiridos. A entrada manual e a
importação estão no [publicador local](LOCAL_AI.md#recortes-visuais-na-alice).

Ensaio exploratório com EmbeddingGemma 2 instalado, quatro objetos desenhados,
fundos e posições trocados, mais um objeto ausente. A consulta estrita pela cena
inteira resolveu 0/4. O recorte resolveu 2/4 e recuperou o vetor de áudio
sintético ligado a cada um. O método regional se absteve nas duas canecas quase
iguais e no objeto ausente. Ao substituir os vetores dos recortes pelos de
outra imagem de propósito, duas consultas recuperaram um momento incorreto.
A geometria do ensaio foi fornecida manualmente. Esses resultados medem a rota
de memória com o encoder instalado e uma amostra desenhada, sem medir acertos
do detector Mirage em cenas reais.

### Propostas automáticas no worker visual

No Windows x64, uma configuração opcional carrega o Mirage local verificado no
mesmo worker finito que codifica a visão. Esse caminho seleciona apenas a geometria
de objetos, descarta caixas com 80% ou mais da área total e deixa o encoder
produzir os vetores. A caixa explícita recebida com a imagem tem prioridade.
Falhas recuperáveis do detector e a ausência de caixas úteis preservam a
aquisição da cena inteira. O relatório diferencia esses casos e informa quantos
recortes foram efetivamente retidos pela atenção. Os arquivos ficam fora do
empacotamento e a execução é opt-in. [Configuração e uso](LOCAL_AI.md#recortes-visuais-na-alice)

O worker real processou em CPU 16 imagens, cada uma nas variantes automática e
manual. Incluiu o ensaio desenhado e três objetos do COIL-100 fotografados de
ângulos diferentes, recortados e compostos sobre fundos artificiais, mais um
objeto ausente em cada família. A cena inteira e o Mirage recuperaram 0/7 momentos
esperados. A caixa manual recuperou 4/7 com o vetor de áudio correto e levou a um
momento incorreto em uma consulta fotográfica. Os dois objetos ausentes não
evocaram episódios. O Mirage reteve caixas em 3/16 imagens, e nenhuma identidade
teve uma caixa retida tanto no registro quanto na consulta. Não há evidência de
ganho na evocação automática nesse recorte. Os casos com fundo artificial não
estimam desempenho em ambientes cotidianos.
[COIL-100, Columbia University](https://www.cs.columbia.edu/CAVE/software/softlib/coil-100.php)

O runtime persistente real também processou duas imagens pelo inbox, com um
recorte retido na primeira e sem proposta útil na segunda. Ambas tiveram recibo
durável de cena adquirida. Ao reabrir, o estado continha os dois momentos e o
recorte original, sem reapresentar as imagens.

### Um som pode evocar um nome aprendido pela visão

Com evocação implícita habilitada, a Alice pode usar um quadro atendido só pela
audição para recuperar a representação visual de um momento anterior. O leitor
visual procura nessa representação um nome ensinado externamente à imagem.
O resultado traz as referências dos momentos que o apoiaram, como associação
recordada. O momento atual continua com áudio apenas, e o leitor de nomes
do áudio não ganha uma associação nova. O painel mostra a última associação
sustentada do último áudio atendido sozinho.

O roteamento compara até quatro momentos anteriores com som e imagem. Uma
semelhança inicial precisa ter cobertura no banco associativo para concorrer.
Se os episódios que passam esse critério divergem ou um deles não recupera
um nome visual, a busca se abstém. Quando há mais de quatro pistas plausíveis,
a busca também se abstém. Uma observação de áudio isolada nunca vira uma
lembrança visual concorrente. Um áudio recebido com atraso não usa um episódio
adquirido depois dele como fonte.

No ensaio com o encoder real, nomes escritos foram ensinados somente às imagens
de dois episódios por família. A busca reconheceu o nome em 4/4 novas variantes
de sons controlados (tom e ruído) e se absteve no som fora do conjunto. Na voz
sintetizada, reconheceu as duas reapresentações exatas, se absteve nas quatro
variações de velocidade ou frase e se absteve na palavra fora do conjunto.
A leitura voltou a funcionar após restauração e o banco direto de nomes do áudio
continuou com zero escritas. O teste usa vetores de arquivos WAV de verdade
e voz sintética em inglês, sem medir compreensão da fala em português,
variação entre pessoas ou identificação de objetos em ambientes reais.

No teste de ponta a ponta, o gateway publicou um PNG e um WAV no mesmo quadro
e o Qwen 0,8B interpretou “Essa imagem se chama maruvi”. O recibo do ensino
registrou apenas a modalidade visual. Uma nova variante do WAV, enviada
sozinha, recuperou Maruvi pela lembrança original. O runtime reabriu com os
dois momentos e a associação disponível, sem reapresentar o par.

### Aprender o som de palavras isoladas

A prática explícita pareia um WAV atendido com a grafia fornecida pela pessoa.
O encoder comum continua guardando o áudio como percepção. A rota de pronúncia
guarda também uma sequência de descritores cepstrais do clipe ensinado. Ela
compara a sequência inteira com os exemplos anteriores, admitindo variação
local de ritmo. A busca usa o melhor exemplo por palavra e se abstém quando
a distância é alta ou as duas palavras mais próximas estão quase empatadas.
Uma consulta não vira exemplo. Arquivos duplicados não reforçam a memória e
uma grafia concorrente para o mesmo áudio é recusada.

O arquivo retém até 32 exemplos, com no máximo quatro por palavra e descarte
dos mais antigos quando necessário. Cada exemplo fica ligado ao momento e ao
SHA-256 do áudio. O resultado não escreve um significado, não altera o nome
visual e não é enviado à LLM como interpretação da fala. O experimento trabalha
com clipes isolados. O painel e o terminal usam o mesmo inbox e os mesmos
recibos, e o runtime real retomou dois exemplos após reabrir as páginas.

Com quatro palavras reservadas e duas vozes sintetizadas em português do Brasil,
um exemplo de cada voz permitiu 16/16 reconhecimentos com mudança de velocidade.
A rota anterior de vetor global acertou 0/16 com a regra de cobertura. Com
apenas uma voz ensinada, o alinhamento acertou 8/8 nessa voz e se absteve nas
8 variações da outra. Os 14 clipes negativos e as oito frases contendo as
palavras conhecidas ficaram sem reconhecimento na rota de clipe inteiro.
O ensaio exploratório de busca dentro de frases confundiu palavras parecidas,
por isso a busca em trechos permanece fora deste modo. As duas gravações humanas
de “casa” também ficaram fora do limiar quando o ensino usou só voz sintética.
O ensaio não estima o desempenho com vozes humanas ensinadas.
[Síntese local do Windows](https://learn.microsoft.com/en-us/uwp/api/windows.media.speechsynthesis.speechsynthesizer)
· [Gravações Lingua Libre](https://commons.wikimedia.org/wiki/Category:Lingua_Libre_pronunciation-por)

## O que precisamos representar

Uma lembrança pode trazer primeiro o acontecimento geral, depois permitir acesso
a aspectos ligados a ele. O exemplo do banho combina atividade, horário, lugar,
temperatura, pressão da água, estado do ambiente, sensações, motivo e acontecimentos
anteriores/posteriores. Nem todos precisam estar acessíveis ou ter sido adquiridos.
O acontecimento continua reconhecível quando alguns detalhes não são recuperados.
O acesso deve funcionar nos dois sentidos: do acontecimento aos detalhes e de um
detalhe ao acontecimento. Um aspecto também pode relacionar episódios diferentes;
essa organização não deve se limitar a uma árvore rígida de pastas e subpastas.

Manter vínculo entre todo e partes: episódio geral, momentos/aspectos e relações
temporais/contextuais. Uma coleção de fichas independentes ou um texto-resumo
gerado pela LLM não demonstra esse vínculo aprendido. Agrupar vetores por média
também não basta se isso mistura acontecimentos ou impede consultar seus detalhes.

Estados internos e motivos podem participar quando há suporte para eles. Registrar
se vieram de percepção, ação própria, relato recebido ou hipótese; não completar
uma experiência específica com todas as propriedades típicas daquela atividade.
Descrições do usuário orientam o fenômeno desejado, sem impor uma fórmula biológica.

## O que orienta a evocação

Um nome pode ativar experiências distintas. Influências candidatas são ambiente,
assunto em foco, intenção atual, pistas perceptivas, recência, reativação, impacto
e relações aprendidas. A influência deve poder mudar com situação e desenvolvimento.
O lugar físico não é uma regra que domina necessariamente o assunto da conversa.

| Situação | Evocação esperada no ensaio |
| --- | --- |
| Em casa, falando das compras | Episódio da compra do macarrão |
| No restaurante, falando do pedido | Episódio do prato pedido |
| No restaurante, falando das compras do mês | Episódio da compra, apesar do lugar atual |
| Nome sem pista suficiente entre experiências semelhantes | Algumas candidatas plausíveis; manter dúvida sobre a referência |
| Pergunta sobre detalhe não adquirido/indisponível | Preservar lembrança geral, sem completar o detalhe como fato |

Evocar uma candidata e afirmar que ela responde a uma pergunta são operações
distintas. Pode haver acesso a várias lembranças antes de decidir qual sustenta
uma resposta. Perguntar ao usuário é uma forma de obter mais informação quando a
distinção importar; não é requisito para toda associação interna.

## Integração pretendida

Preservar NativeMoments como impressões sensoriais endereçáveis e criar vínculos
aprendidos entre essas impressões e episódios mais abrangentes. O episódio deve
oferecer acesso geral e acesso por aspecto, preservando identidade e origem dos
momentos. Contexto precisa ter suporte nas entradas/estado do agente; stream_id,
posição na lista ou rótulo pronto do avaliador não substituem contexto semântico.

Separar, para avaliação, pistas do ambiente e do assunto atual. A ligação entre
elas deve poder ser aprendida e revisada, em vez de uma lista fixa de lugares e
palavras com respostas programadas. A implementação pode organizar componentes,
mantendo comunicação e adaptação entre eles durante a interação. Bases pré-treinadas
estáveis são ponto inicial; plasticidade das conexões/representações permanece
parte da meta e exige medir compatibilidade com o conhecimento anterior.

Reativação pode aquecer episódio e detalhes de maneiras diferentes. Importância
não garante acesso permanente; repetição de exposição/evocação não comprova por
si só que todos os aspectos foram conservados. Atualizar um detalhe ou corrigir
um relato deve preservar os demais e distinguir o que se pensava antes do atual.

Toda adaptação usa o proprietário, relógio e orçamento existentes. Sono não é
condição para aprender, recordar ou comunicar conhecimento entre componentes.
Consolidação pode ter ritmos mais lentos e executar em segundo plano; quiet também
pode ser apenas quiet. A referência Sleep orienta mecanismos de estabilização,
sem adotar uma fronteira obrigatória entre interação e aprendizagem duradoura.

## Primeiro ensaio e controles

Contrato prévio do ensaio contextual (01/11): preferências RLS sobre interações
de projeções DCT16 do estado atual e do contexto anterior guardado nos pesos por
episódio; além de frescor/reativação/impacto/modalidades. Feedback externo de uma
evocação realmente feita atualiza somente relevância, com crédito de uso único e
TTL60s; não fornece um alvo factual. Guardar o contexto que precedeu a experiência,
sem reconstruir contextos ausentes de estados antigos.

Currículo não verbal com duas experiências de um objeto/pista comum, sons distintos
e contextos distintos. Duas pistas de ambiente e duas de assunto são codificadas
por vetores ortogonais aleatoriamente rotacionados no espaço128; rótulos semânticos
só existem no gerador de feedback. Três combinações ambiente–assunto entram no
treino; a quarta fica reservada. Foco deve poder contrariar o ambiente.96 feedbacks
online por seed17/29/71, até60s por seed,CPU1, sem LLM/encoder/nomes. Uma pausa
temporal de120s controla estado transitório entre situações; não é fase de treino
no sono, e não produz dados de intervalo. Avaliar16 consultas com pequena variação
perceptiva, incluindo restaurante/compras e a combinação não vista. Critério:
>=90% geral e nesses dois recortes; ganho>=25p.p. sobre política sem aprendizagem.
Apagar política/contextos separadamente deve remover o benefício; apagar conteúdo
episódico deve remover representações. Restore sem reapresentar feedback deve
conservar a preferência. Máximo2 evocações/4 páginas; snapshot e política dentro
do orçamento existente. Se falhar, registrar e revisar sem baixar exigência.

Usar experiências compostas com palavra/objeto recorrente em ambientes e assuntos
diferentes. Reservar combinações ambiente–assunto e variar símbolos por semente,
para uma regra lexical fixa não resolver o ensaio. Ensinar por experiências e
feedback; não entregar o ID da resposta nem um resumo completo durante a consulta.

Avaliar separadamente acesso ao episódio geral, acesso a detalhes, relações antes/
depois, influência do contexto e preferência dinâmica entre candidatas. Incluir
conflito ambiente–assunto, lembrança antiga relevante versus recente irrelevante,
detalhes ausentes, relatos corrigidos e episódios parecidos. Apagar pesos de
vinculação e de conteúdo separadamente: metadados intactos não podem sustentar
respostas factuais sozinhos. Repetir após restart, sem reapresentar as experiências.

Conservar o teste sem mudança de contexto como referência, medir interferência e
custo das atualizações online. Critérios e orçamento concretos devem ser registrados
antes do próximo treino reservado; falha exige rever hipótese, não reduzir exigência.

## Integração com diálogo e retorno de relevância — contrato de01/11

No modo implícito experimental, uma menção literal a um nome aprendido pode
evocar até duas representações sensoriais antes da expressão. O nome evoca seu
writer aprendido; não fornece a resposta desejada nem seleciona um episódio por
conter um relato. Guardar referências/hashes e crédito da evocação principal,
sem mandar vetores como texto para a LLM. Ambiguidade factual continua distinta:
evocar duas candidatas não autoriza escolher quem fez algo. Legados sem modo
implícito conservam comportamento anterior.

Validar o contexto capturado sem reevocar/aquecer a cada poll; alterações das
evidências usadas, de uma resposta factual única ou perda de conteúdo invalidam
o contexto antes de responder. Percepções de fundo continuam sendo aprendidas;
não esvaziam o foco da resposta já em geração. Mais candidatas quando a referência
já era ambígua não tornam falsa uma evocação capturada com instante explícito.
Idle e a própria reativação não causam revisão infinita. O retorno explícito de
relevância aponta para uma conversa concluída e sua evocação realmente feita;
não é aprovação social, correção factual nem uma escolha livre de ID episódico.
Uso único/TTL60s/histórico16 continuam valendo. Não estender o prazo se a expressão
demorar; oferecer retorno apenas enquanto o crédito existir.

Testes necessários: menção sem tópico manual com duas experiências semelhantes,
mudança não verbal sem nova percepção, fatos ainda ambíguos, retorno alterando
somente preferência, replay/expiração, quiet, ablação de fatores, mudança durante
expressão, retomada e registros antigos. Primeiro protocolo com backend de teste;
qualidade linguística e admissão de um modelo real são avaliações separadas.

## Fluxo sem esvaziar o estado — ensaio de01/11

### Contrato prévio

Usar sementes17/29/71 e96 consequências externas por semente, com o mesmo
critério>=90% em16 consultas e nos recortes de conflito/combinação reservada.
Agora cada consulta adquire uma pista visual real pelo caminho observe, além do
quadro ambiente/assunto; intervalo0,2s entre situações e0,1s até a pista. Não
zerar working/contexto nem apagar as novas impressões para facilitar evocação.
As novas pistas sem som devem permanecer como experiências distintas, sem ganhar
o som recordado como se tivesse sido escutado. A evocação é a automática devolvida
por observe; o avaliador pode ler seu primeiro banco, sem escolher outra memória.
Alvo e rótulos ficam somente no feedback/avaliação. Máximo2 evocações/4 páginas.

Avaliar o mesmo estado inicial restaurado com política aprendida e com pesos da
política zerados, usando a mesma sequência de entradas. Exigir ganho>=25p.p.;
verificar fatos antigos inalterados, continuidade da contagem de experiências,
ausência de som nas pistas novas e persistência sem reapresentar feedback. CPU1,
até90s por semente, sem linguagem/encoder ou janela. Falha é diagnóstico; não
transferir a aprovação do ensaio com intervalos120s para esse fluxo.

Diagnóstico inicial: créditos não respondidos saturaram o histórico16, impedindo
novos retornos. Correção: substituir o crédito mais antigo, preservando IDs e
recusando retornos sobre créditos retirados, sem apagar experiências. Depois
disso, seeds17/29/71 tiveram14/16,16/16 e13/16; combinação reservada2/4,4/4 e1/4.
O currículo contínuo não foi aprovado. Fatos originais permaneceram iguais e
as novas pistas sem áudio não receberam áudio fabricado.

Hipótese de revisão: um valor de relevância negativo, com pouco suporte no
contexto novo, está penalizando uma lembrança apoiada mais do que uma candidata
sem preferência aprendida. A inspeção da semente17 encontrou esse caso. Testar
contribuição aprendida multiplicada por1/(1+variância RLS), mantendo os limites
anteriores; essa variância não é uma probabilidade calibrada. Regra fornecida de
atenuação simétrica, sem identificar episódio correto ou favorecer modalidade.
Preservar leitura antiga em checkpoints de política1; política2 registra a nova
regra. Seeds17/29/71 passam a ser desenvolvimento. Antes de qualquer rodada
revisada, reservar41/53/89 para avaliação, com os mesmos96 feedbacks e critérios,
sem ajustar a regra depois de ver seus resultados. Se falhar, registrar falha.

### Resultado da revisão

A regra atenuada passou na semente de desenvolvimento17 e nas três reservadas
41/53/89:16/16 consultas em cada,4/4 no conflito e4/4 na combinação reservada.
Os controles restaurados do mesmo estado com pesos da preferência zerados
ficaram em8/16. Não se alterou a regra após ver essas três sementes.

Cada estado de treino contém196 impressões, incluindo as96 novas pistas visuais
adquiridas durante o aprendizado, e96 atualizações da preferência. A avaliação
adiciona32 impressões por estado, em vez de descartar as consultas. Novas pistas
mantiveram máscara somente visual; fatores originais não mudaram. Uma auditoria
em processo novo leu os três arquivos native.pt e acertou48/48 consultas sem
feedback, conservando pesos da preferência, fatos originais e arquivos-fonte.

Uma segunda auditoria restaurou as três políticas1 antigas, confirmou a regra
covered-linear-v1 e passou48/48 consultas do currículo anterior. O snapshot novo
da política é2 e explicita read_rule; NativeGrounding permanece10/core57/58.
Não migrar uma preferência treinada para outra regra silenciosamente.

Passaram8 contratos contextuais,9 reativação,11 runtime, CI e build Release.
Provas em continuous-recall-v2/v3-20261101-*, continuous-recall-fresh-audit-20261101
e continuous-recall-legacy-audit-20261101, sob bin/AliceMemory. O piloto inicial
com histórico saturado e os resultados v2 reprovados foram preservados.

Limites: fluxo sequencial simulado de dois tipos de situação e pista recorrente,
vetores128D controlados, intervalos0,2/0,1s no relógio do agente; não é medição de
captura ao vivo, nem de mudanças semânticas reais no diálogo. A atenuação pela
variância é uma escolha de arquitetura, não confiança humana calibrada. Ainda
faltam feedback conversacional dessa política, episódios mais abrangentes e
avaliação de interferência em currículos prolongados e diversos.

## Seleção contextual com intervalos120s — resultado de01/11

O ensaio com intervalos120s passou nas três sementes17/29/71:16/16 consultas por semente,
incluindo conflito ambiente–assunto e a combinação reservada. Zerar os pesos da
preferência ou o contexto episódico reduziu cada resultado a8/16. Remover os
fatores de conteúdo eliminou as representações recuperadas, apesar de preservar
as rotas. Uma auditoria em processo novo restaurou os três snapshots com o decoder
atual e acertou48/48 novas consultas, sem reapresentar feedback ou mudar os pesos
da preferência. São consultas adicionais ao mesmo mundo sintético, não48 mundos.

RecallContexts guarda nos pesos o estado de trabalho anterior a cada experiência;
RecallPreference aprende a relevância de uma evocação realmente executada com
consequência externa. O retorno altera a preferência, não o conteúdo factual nem
o número de experiências. Crédito tem uso único e expira; contextos ausentes em
estados antigos permanecem desconhecidos. Retirada de momentos preserva os
endereços das linhas restantes. NativeGrounding10 persiste contexto e política;
formatos1–9 continuam legíveis e core57/58 não muda. Sem contextos novos, o modo
experimental ainda pode produzir9; o padrão legado continua8.

Provas locais: contextual-recall-pilot-20261101-seed17,
contextual-recall-20261101-seed29/seed71 e
contextual-recall-fresh-audit-20261101.json em bin/AliceMemory. Os relatórios dos
treinos verificaram a ordem restaurada; a auditoria posterior verificou novas
consultas sem treino. Seis contratos novos, nove de reativação e onze de runtime
passaram; CI e build Release passaram.

Limites:96 feedbacks por semente, contextos sintéticos rotacionados128D, projeção
fornecida DCT16, bônus aprendido limitado por ganho0,5 e mistura fornecida0,25.
Sem nomes, LLM ou encoder nesses ensaios. Os intervalos simulados120s isolam
contexto transitório; mudanças sobrepostas no fluxo contínuo ainda precisam de
avaliação. O feedback tipado da API nativa não está ligado à conversa/painel.
Ainda falta extrair foco semântico de uma conversa real e representar episódios
abrangentes com seus detalhes. Isto não resolve a ambiguidade factual204/215,
não demonstra sensação de calor nem entendimento geral.

## Primeiro incremento e diagnóstico de01/11

Primeiro incremento implementado em modo experimental: separar a recuperação sensorial de candidatas
da decisão factual única. related() deve ler até dois momentos em bancos distintos,
com no máximo quatro leituras de página, sem fundir seus conteúdos. Modo implícito
experimental pode reativá-los após uma percepção adquirida e influenciar o estado
de trabalho usado nas próximas decisões, sem nomes ou chamada de linguagem.
Ativar depois de aprender os alvos do estímulo atual evita vazamento de alvo para
previsões/associações desse mesmo estímulo. O momento recém-adquirido fica excluído.

Protocolo antes do ensaio: dois acontecimentos com pista visual comum e sons
distintos; pista visual posterior deve reativar os dois sons separadamente nos
pesos, sem registrar sons novos. Controle sem reativação, pesos apagados, quiet,
tempo ocioso, saída própria, falha de leitura e retomada. Fonte real204/215 também
deve poder ser lida como duas evocações sensoriais, sem LLM/encoder e sem procurar
uma resposta textual. CPU1, máximo2 resultados/4 páginas por percepção. A prioridade
e o ganho inicial eram políticas fornecidas, antes do ensaio contextual acima.
Conserva padrão anterior nos estados legados; modo experimental é explícito.

Resultado: teste não verbal aprendeu associação imagem→som sem nomes; depois dois
nomes inventados foram vinculados ao mesmo significado sensorial. Testes distinguem
os sons de dois momentos com pista visual comum, mudança de estado de trabalho/
contexto preditivo, entrada para a próxima política de atenção, falta de som na
nova percepção, ablação, quiet/idle/self, falha de leitura e retomada. O ganho fixo
é experimental; naquele incremento a influência contextual não era aprendida. Não é demonstração
de sensação subjetiva ou de um novo sentido térmico. As entradas são vetores
perceptivos controlados; não treinou um encoder do zero.

nonverbal-reactivation-real-20261101-v2 recuperou204/215 como representações
visuais separadamente endereçadas, com o mesmo conteúdo visual, a partir de uma
pista nos pesos de nome. Sem encoder/LLM ou nova experiência. Zerar os fatores
de conteúdo deixou as rotas mas removeu as representações recuperadas. Ativação
mudou estado não verbal, aqueceu fontes uma vez, preservou nomes/fatos/contadores,
e foi restaurada. Isso não resolve a escolha factual da pergunta sobre dono.

CLI experimental: --native-implicit-recall / --no-native-implicit-recall; omitir
preserva a configuração restaurada. NativeGrounding8 continua padrão;9 marca modo
ativo sem contexto armazenado;10 conserva a política/contextos novos. O estado
de trabalho e o contexto preditivo já são tensores persistentes.
Não há varredura compulsória no idle nem narrativa enviada à LLM a cada evocação.
Não adquirir saída sintética como percepção nova é uma regra de proveniência,
não uma proibição de futuros mecanismos de aprendizagem por pensamento/hipóteses
ou de perceber ações próprias com retorno sensorial verificado.

dialogue_recall.py reconhece menções literais a nomes aprendidos, evoca writers,
consulta memória sensorial e lê interpretação nos pesos. O protótipo só entrega
um relato quando o episódio e a relação são únicos. Há testes de ablação, atenção,
revisão e restauração; ainda não representa os episódios integrados acima.

O estado real dialogue-real-v2 tem duas impressões da mesma imagem em204 e215.
O episódio204 não tem relato;215 tem relações autor e dono. A consulta por hami
encontra ambos e para em ambiguous_moments. Isso expõe uma limitação de seleção,
não uma prova de que esqueceu a informação. Não eliminar204 nem selecionar215
porque contém a resposta desejada. Usar o diagnóstico para avaliar evocação de
candidatas e discriminação contextual, com dados reservados.

O ensaio completo com novo texto/encoder também aguardou RAM e terminou sem nova
aquisição: não foi aprovado. Artefatos locais dialogue-auto-real-20261101-v1,
dialogue-auto-lookup-20261101.json e dialogue-auto-ambiguity-20261101.json conservam
os dois diagnósticos, sem tratá-los como demonstração da arquitetura pretendida.
