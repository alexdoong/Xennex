# Central pessoal de análise de jogos

Status: arquitetura e plano, registrados em 2026-09-13. Consulte a primeira entrega ao final. As funcionalidades
abaixo descrevem a visão completa; somente o recorte indicado ao final foi implementado. Nome definitivo da área em aberto.

## Visão

Transformar a área de WuWa em um espaço pessoal para registrar jogos, estudar
referências, acompanhar evolução, comparar escolhas e experimentar cenários.
WuWa será o primeiro módulo especializado, sem limitar a estrutura aos seus
personagens ou atributos. LoL, osu! e jogos de cartas terão suas próprias regras.
A futura Alice poderá consultar essa base e solicitar cálculos reproduzíveis.

O ciclo de uso é: registrar → contextualizar → comparar → simular → experimentar
no jogo → registrar o resultado. A informação precisa ajudar a responder uma
pergunta, além de existir em um painel.

## Estado atual verificado

- `frontend/src/features/wuwa/WuWaTab.tsx` apresenta um botão de sincronização
  demonstrativo; não existe coleta implementada nessa tela.
- `src/Models/WuWaBuild.cs` representa uma build de WuWa, incluindo equipamento,
  atributos em texto e imagens locais.
- `src/Services/ConfigService.cs` carrega e salva essa build em
  `Data/wuwa_build.txt`. Esse formato não oferece histórico de versões.
- A menção atual a Prydwen e Akasha na interface não comprova uma integração,
  nem que ambos disponibilizem dados compatíveis com WuWa.

## Experiência de uso

1. Biblioteca: jogos e perfis, favoritos e perguntas de análise salvas.
2. Visão do jogo: últimos registros, evolução e notas relevantes.
3. Histórico: sessões e partidas em uma linha do tempo, com builds, patch,
   contexto, observações e anexos associados.
4. Comparação: selecionar registros ou versões lado a lado e destacar diferenças.
5. Laboratório: duplicar um cenário, alterar parâmetros e comparar resultados,
   mostrando hipóteses, fórmula, limitações e decomposição do cálculo.
6. Fontes: cadastrar referências, importar arquivos, acompanhar atualizações e
   verificar a origem dos dados usados nas análises.

Filtros por período, patch, personagem, modo e outros contextos do jogo devem
acompanhar gráficos e tabelas. Oferecer detalhes progressivos e vistas salvas;
evitar colocar todas as métricas simultaneamente na tela inicial.

## Núcleo compartilhado e módulos de jogo

| Núcleo | Responsabilidade |
| --- | --- |
| Jogo e perfil | Identidade do jogo, conta opcional e preferências |
| Registro de sessão | Data do acontecimento, resultado, contexto e notas |
| Build versionada | Configuração completa em cada revisão, sem sobrescrever o passado |
| Métrica | Identificador, valor numérico, unidade e definição versionada |
| Referência | Origem, URL ou arquivo, data de coleta e versão do importador |
| Cenário e execução | Entradas, modelo, versão, resultados e hipóteses |
| Anexo | Imagens e arquivos locais associados aos registros |

Cada módulo define atributos, validação, entidades, filtros e cálculos do seu
jogo. Não converter todo jogo em um `WuWaBuild` com campos opcionais. Tampouco
criar um serviço único responsável por armazenamento, coleta, cálculos e tela.

Estrutura sugerida, a criar conforme as primeiras funcionalidades exigirem:

```text
src/Models/GameAnalytics/              contratos e modelos compartilhados
src/Services/GameAnalytics/Storage/    persistência e migrações
src/Services/GameAnalytics/Imports/    importadores e proveniência
src/Services/GameAnalytics/Games/      regras e cálculos por jogo
frontend/src/features/games/          biblioteca, histórico e comparações
frontend/src/styles/games.css         estilos limitados ao contêiner da área
scripts/game_sources/                 coletores opcionais e independentes
```

Serviços C# executam regras e persistência; `ApiBridge` apenas despacha contratos
tipados em `webview.d.ts`. React exibe e manipula esses contratos, com componentes
pequenos. Operações demoradas devem ser canceláveis e não bloquear a interface.

## Histórico, qualidade e armazenamento

Proposta: SQLite local em `Data/`, com migrações transacionais e backup antes de
migrações. Anexos ficam em diretório separado com caminhos relativos. A adoção da
biblioteca SQLite exige validar também o empacotamento self-contained existente.

Metadados consultáveis ficam em tabelas próprias; conteúdo específico de cada
jogo pode usar documentos com esquema versionado e validado. Evitar um arquivo
JSON monolítico reescrito a cada partida.

Cada registro deve distinguir:

- Quando aconteceu e quando foi importado; armazenar datas com fuso definido.
- Patch do jogo e versão do conjunto de dados utilizado, inclusive desconhecidos.
- Medição real, entrada manual, referência externa e resultado simulado.
- Valor ausente e valor zero; unidade original e conversão aplicada.
- Revisão da build, parâmetros e versão da fórmula usados no cálculo.

Execuções preservam suas entradas: atualizar uma referência não recalcula nem
altera silenciosamente o histórico. Um recálculo cria outra execução comparável.
Importações repetidas devem reconhecer registros já existentes, oferecer prévia
e relatório de erros e manter os dados válidos anteriores se a coleta falhar.

Migração de WuWa: importar o arquivo legado uma única vez, preservando o original
e identificando a importação para evitar duplicatas. Validar números em texto,
separadores decimais, porcentagens e imagens ausentes. Data de criação e patch
desconhecidos permanecem desconhecidos; a data de importação não os substitui.

Dados pessoais, anexos, credenciais e banco não entram no Git ou na release.
Exportação e restauração devem usar formato versionado e incluir anexos opcionais.

## Análises especializadas

| Jogo | Registros e comparações | Laboratório |
| --- | --- | --- |
| WuWa | Builds, atributos, equipe, equipamentos e rotações | Comparar equipamentos sob a mesma rotação, buffs e alvo |
| LoL | Partidas, função, campeão, composições, itens e momento de compra | Hipóteses de build e análise histórica por contexto |
| osu! | Mapa, modo, mods, precisão, combo e resultado | Comparar tentativas equivalentes e acompanhar consistência |
| Cartas | Jogo e regras específicos, deck, mão, ações e estado conhecido | Probabilidades de compra e ramificações de jogadas |

Calculadoras só entram como funcionais quando houver fórmulas documentadas e
casos de referência verificáveis. Não inventar um cálculo de dano genérico para
preencher a interface. Separar aritmética determinística de heurísticas.

Comparações devem mostrar tamanho da amostra e diferenças de contexto. Vitória
após trocar um item não demonstra sozinha que o item causou a melhora. Mudanças
de patch, mapa, dificuldade, adversário ou modelo de pontuação podem inviabilizar
uma comparação direta.

Para cartas, começar com regras de um jogo definido. Informação desconhecida
vira hipótese explícita. Se houver simulação amostral, registrar semente, número
de execuções e incerteza. Enumerar todos os estados possíveis não é requisito
realista para qualquer jogo.

## Fontes e coleta

Começar por entrada manual e importação estruturada. Integrar fontes externas
por adaptadores independentes, preferindo APIs oficiais quando disponíveis.
Cada adaptador declara jogos suportados, formato, autenticação, frequência de
atualização, validações e estado da última execução.

Scripts de scraping produzem dados intermediários validados antes da entrada no
banco. Definir timeout, limites de requisição, cache e tratamento de alterações
na página. Guardar a origem e as premissas de recomendações; fontes divergentes
permanecem identificadas, sem mesclar seus números silenciosamente.

Referências para avaliar durante a implementação de cada conector:

- Riot: https://developer.riotgames.com/docs/lol — dados e APIs oficiais;
  credenciais não devem ser incluídas no executável ou repositório.
- osu!: https://osu.ppy.sh/docs/ — API e autenticação oficiais.
- Prydwen: https://www.prydwen.gg/wuthering-waves/guides — referências de WuWa;
  verificar formato e condições de acesso antes de automatizar uma seção.
- Akasha: confirmar a página e o jogo desejados antes de definir o adaptador;
  não presumir uma API pública ou suporte a WuWa.

Não implementar coleta contínua de todos os sites como requisito inicial.
No LoL, começar por histórico e cenários manuais; assistência durante partidas
seria outro escopo, sujeito às capacidades e regras oficiais da integração.

## Integração futura com Alice

Expor operações estruturadas de consulta, comparação e execução de cenários.
As respostas devem trazer identificadores dos registros, fontes e premissas.
Alice poderá explicar resultados e propor hipóteses; cálculos ficam nos módulos
testáveis. Escritas futuras devem seguir validação e histórico de alterações.
O aplicativo continua útil sem Alice ou conexão com um serviço de IA.

## Sequência de entrega e critérios de aceite

1. Base utilizável: biblioteca de jogos, registros manuais, notas, métricas,
   persistência, exportação e histórico visual. Aceite: criar e editar registros,
   reiniciar o app, filtrar períodos e restaurar uma exportação sem perder dados.
2. WuWa: versões de builds e migração do legado. Aceite: comparar revisões com
   diferenças explícitas, preservar imagens disponíveis e não duplicar importação.
3. Primeiro cálculo de WuWa com escopo definido: entradas explícitas, premissas
   e resultados verificáveis. Aceite: casos de referência e repetibilidade.
4. Integrações graduais: um conector por vez, depois módulos LoL e osu! conforme
   prioridade. Aceite: erros de rede, repetição e mudança de formato não corrompem
   registros; dados reais permanecem distinguíveis de estimativas.
5. Cenários avançados, módulo de cartas e acesso da Alice: após validar regras
   concretas, fontes e o fluxo de análise das entregas anteriores.

Esta proposta não muda a versão 0.2.3 nem representa uma nova release. A evolução
da análise de jogos pode ser entregue em etapas sem tratar o streaming como
concluído. Cada implementação deve seguir `docs/CODING_RULES.md` e as validações
de empacotamento existentes.

## Primeira entrega implementada — 2026-09-13

A navegação agora exibe **Jogos**, preservando o identificador interno `wuwa-db`.
A tela demonstrativa foi substituída pela biblioteca de jogos personalizados,
registros manuais editáveis, notas, contexto, patch e até 12 métricas por registro.
Há filtros por período/texto, gráfico de observações e comparação de dois registros.

A exportação JSON contém um jogo completo. A importação oferece prévia e cria
uma cópia independente, preservando datas e conteúdo, sem sobrescrever jogos.
Não há sincronização externa, calculadora, migração da build WuWa ou integração
com Alice nesta entrega. O arquivo legado `Data/wuwa_build.txt` permanece intacto.

Decisão de implementação inicial: um documento JSON versionado por jogo em
`Data/games/<id>.json`, inicialmente limitado a 2.000 registros e 4 MB (ampliado para 32 MB na etapa visual). Gravação temporária,
flush e substituição atômica mantêm a versão anterior em `.json.bak`.
Uma revisão otimista impede sobrescrever alterações com um estado desatualizado.
Arquivos corrompidos geram aviso e são preservados; recuperação não é automática.
É possível importar um backup válido como cópia escolhendo o arquivo no seletor.

SQLite permanece como evolução planejada para maior volume e consultas entre
jogos. A versão de esquema e os contratos da ponte isolam essa futura migração.
O editor de registros corrige o estado atual; não é um histórico de revisões de
builds. Essas revisões pertencem à etapa especializada de WuWa.

O hub de vida e rotina existente no Google AI Studio foi registrado separadamente
em [FUTURE_LIFE_HUB.md](FUTURE_LIFE_HUB.md). Compartilhamento futuro de componentes
não implica armazenar compromissos ou tarefas como jogos.

Validações: `scripts/tests/GameAnalyticsTests/` cobre armazenamento e importação;
`frontend/tests/games-ui.test.mjs` cobre o fluxo visual com dados fictícios.

## Espaço visual — 2026-09-13

A entrada do jogo agora abre o espaço visual. O histórico permanece em uma
subárea própria. É possível escolher uma capa e criar personagens (ou peças
de jogo) com imagem pessoal, categoria, cor, notas e enquadramento vertical.

Em **Planejamento**, crie quadros, adicione personagens e anotações, arraste
cartões, edite instruções e conecte passos com setas. As setas do teclado movem
o cartão selecionado; Shift aumenta o passo. O zoom pode ser ajustado ou
adaptado ao espaço disponível. Duplicar um plano cria cartões e conexões
independentes para explorar uma alternativa.

**Salvar espaço visual** persiste o conjunto; **Descartar alterações** volta
ao último estado salvo. Os rascunhos permanecem ao navegar para outra aba do app,
mas precisam ser salvos antes de fechar o aplicativo. Enquanto um personagem
está em edição, aplique ou cancele essa edição antes de salvar o conjunto.
Uma falha de gravação mantém o rascunho para nova tentativa.

Remover um cartão remove suas conexões. Remover um personagem do elenco mantém
os cartões existentes como anotações, preservando títulos e instruções.
A edição de personagem atualiza sua imagem nos cartões que o referenciam.
Os planos são manuais; ainda não calculam dano, validam regras ou executam ações.

### Formato e compatibilidade

O esquema passa a **2**. Arquivos do esquema 1 são lidos com um espaço visual
vazio, preservando as sessões. A leitura não regrava o arquivo; o primeiro
salvamento guarda o original no backup. Versões antigas do app não entendem o
novo esquema e não devem ser usadas para editar esses arquivos.

As imagens PNG, JPEG e WebP escolhidas pelo usuário são otimizadas localmente
em WebP e incorporadas ao documento. A exportação inclui capa, personagens,
planos, posições e conexões. Não há upload nem dependência do caminho original
da imagem. Limites atuais: 100 personagens, 24 planos, 60 cartões e 120 conexões
por plano, 2.000 sessões e 32 MB por jogo. Os limites são validados antes de gravar.

A ponte C# continua a delegar aos serviços; GameVisualValidation valida as
imagens e referências entre elementos. Nenhum dado pessoal entra no pacote.
O hub de rotina permanece uma integração futura, conforme FUTURE_LIFE_HUB.md.

### Testes adicionais

`frontend/tests/games-visual.test.mjs` exercita upload, enquadramento, arraste
com escala, teclado, conexões, duplicação, rascunho entre abas, falha de gravação,
exportação/importação, recarga, remoção e layout estreito.
O teste nativo também verifica imagens, posições e conexões após reiniciar.

## Definição livre dos jogos e cenários — 2026-09-13

A visão do usuário é descrever primeiro o jogo e as variáveis relevantes para
depois observar, comparar e futuramente prever resultados. Um catálogo fechado
de skills não atende: macro, controle de mapa, controle de campos e outros nomes
pessoais devem ser cadastráveis. Habilidades do jogador e habilidades/ações dos
personagens são conceitos separados.

Na criação, **Modelo inicial** oferece Personalizado, Ritmo e execução,
Estratégia e personagens e Cartas. São sugestões editáveis, não classificações
obrigatórias. **Definir jogo** permite escrever outro tipo e configurar:

- Uso de personagens/cartas/peças, nome da galeria e presença de ranking.
- Habilidades do jogador com nome e descrição livres.
- Ações do jogo: usar habilidade, trocar personagem, comprar item, jogar carta etc.
- Métricas com nome, unidade, critério de medição, habilidade relacionada opcional
  e interpretação (maior, menor ou dependente do contexto).
- Campos de contexto: build, equipe, mapa, mods, adversário, deck, tipo de carta
  ou qualquer outra condição desejada.

A galeria pode ser desativada sem apagar suas imagens ou quadros. Jogos de ritmo
abrem na visão de habilidades; jogos com peças oferecem galeria e habilidades.
Arquivar uma definição preserva referências históricas e a retira das novas
opções de registro.

### Registros e análise disponíveis

Os registros agora usam as métricas cadastradas e permitem preencher contextos
separadamente. A sequência de ações registra tempo relativo em segundos, ação,
ator, detalhes e resultado numérico opcional ligado a uma métrica definida.

O histórico filtra os contextos e permite escolher entre resultados da sessão
ou resultados das ações. O agrupamento por condição mostra quantidade, média,
mínimo e máximo. Assim, Build A e Build B, por exemplo, podem ser comparadas no
mesmo indicador, considerando os demais filtros. Tempo das ações parte da data
e hora informada para o registro.

Esses são registros e resumos de observações manuais. Ainda não há previsão
automática, motor de regras de cada jogo, cálculo de dano, importação de partidas
profissionais ou geração automática de todas as combinações possíveis.
Builds como conjuntos versionados de itens também continuam uma etapa própria;
atualmente a identificação da build pode ser um campo de contexto.

### Persistência

Esquema **3** inclui Definition, ContextValues, Events e identificadores de
métricas. Arquivos 1/2 continuam legíveis: a migração cria um catálogo das métricas
legadas com IDs determinísticos, sem regravar o original na leitura.
Acima de 100 métricas distintas legadas, as excedentes mantêm seus valores como
registros não classificados. O primeiro salvamento mantém o backup existente.

Nomes/unidades de observações e ações são snapshots. Renomear definições não
reescreve esses snapshots; unidades diferentes não são agregadas na mesma série.
Referências inválidas são rejeitadas antes da gravação. Limites: 100 entradas por
catálogo, 50 contextos e 120 ações por registro, além dos limites já documentados.

Testes: GameAnalyticsTests cobre migração, referências, arquivamento e snapshots;
games-definition.test.mjs cobre modelos, skills livres, contextos, resultados de
ações, gráficos agrupados, preservação histórica e a galeria de cartas.
