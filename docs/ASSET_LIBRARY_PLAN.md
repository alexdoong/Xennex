# Biblioteca visual e explorador do Xennex — plano de implementação

Data: 28/09/2026. Status: implementação inicial em teste. Consulte [ASSET_LIBRARY.md](ASSET_LIBRARY.md) para o comportamento efetivamente entregue e os limites atuais. Este plano também registra metas futuras, que não devem ser interpretadas como recursos já disponíveis.
Nome de trabalho: **Biblioteca**. Versão do aplicativo permanece a definida no csproj.

## Incremento de nomenclatura em lote (01/10/2026)

Status: implementado e validado; uso e limites em ASSET_LIBRARY.md.

Contrato: `AssetFileRequest` recebe regra declarativa de numeração e decisões
por ID (renomear/ignorar), mantendo a ordem explícita de `AssetIds`. O backend
calcula o maior número compatível nas pastas de destino, preserva extensões e
reserva nomes de todo o lote. A prévia distingue conflitos, itens ignorados e
destinos aceitos; somente planos resolvidos com itens ativos podem executar.
A interface oferece padrão `{base}{number}`, preenchimento com zeros, início
manual ou continuação automática, aplicação a todos/apenas conflitos e ordenação
por nome/data ou manual com miniaturas. Colisões nunca autorizam sobrescrever.
Renomear em lote usa o histórico existente. Trocas cíclicas de nomes ocupados
continuam recusadas, sem movimentações temporárias implícitas.

## 1. Decisão do usuário e resultado esperado

O usuário quer duas experiências completas sobre o mesmo acervo:
**Galeria**, para visualizar e comparar artes, e **Explorador**, para organizar
arquivos e pastas. Não reduzir a entrega a uma grade de imagens com tags.
As duas visões devem compartilhar busca, seleção, favoritos, tags e coleções.

A entrega será incremental, mas a primeira versão funcional completa compreende
os marcos M0–M4 abaixo, incluindo operações reais de arquivos. Canvas, busca por
cor e integrações avançadas são expansões previstas, não promessas já cumpridas.

Fluxos principais:
1. Adicionar pastas escolhidas pelo usuário, inclusive a saída do ComfyUI.
2. Navegar por artes visualmente ou alternar para arquivos/pastas.
3. Encontrar imagens por nome, tags, dimensões e metadados disponíveis.
4. Selecionar variações, comparar, favoritar e organizar em coleções.
5. Criar pastas, renomear, copiar, mover e enviar arquivos à Lixeira.
6. Retomar a mesma seleção e localização depois de trocar de visão ou reiniciar.

## 2. Referências e pesquisa de preferências

A pesquisa inicial e a matriz de decisões estão em
[ASSET_LIBRARY_REFERENCES.md](ASSET_LIBRARY_REFERENCES.md).
As referências inspiram comportamentos; não copiar identidade visual nem código
sem verificar sua licença. A experiência final deve respeitar as skins do Xennex.

A documentação de produto confirma recursos, mas não comprova satisfação dos
usuários nem superioridade universal. Comentários de comunidades devem ser
registrados como relatos individuais, com URL, versão e data. Preferências do
usuário ainda não expressas ficam como hipótese, nunca como decisão aprovada.

## 3. Experiência visual proposta

Estrutura comum da aba:

| Região | Conteúdo |
| --- | --- |
| Topo | Voltar/Avançar, caminho navegável, busca, Galeria/Explorador e opções de visualização |
| Esquerda recolhível | Pastas cadastradas, Recentes, Favoritos, Sem tags, Tags, Coleções e buscas salvas |
| Centro | Galeria ou explorador; nenhum painel de configuração permanente sobre as artes |
| Direita recolhível | Prévia, propriedades, tags, notas e detalhes de geração do item selecionado |
| Rodapé discreto | Quantidade, seleção, tarefas em andamento, progresso e opção de pausar |

Galeria: grade virtualizada com tamanho de miniatura ajustável, proporção original
por padrão e opção de recorte; fundo neutro/checkerboard para transparência.
Duplo clique abre visualizador; zoom 100%, ajustar à tela, pan, setas anterior/
próxima, tela cheia e Escape. Comparar inicialmente 2–4 imagens, com zoom
independente e opção de sincronização. Carregar originais somente quando usados.

Explorador: árvore de pastas, caminho com breadcrumbs, grade/lista de detalhes,
ordenação por nome/data/tamanho/tipo, atalhos, seleção múltipla e menu contextual.
Lista todos os tipos de arquivo nas pastas cadastradas; a galeria filtra os
formatos visuais suportados. Tipos sem prévia recebem ícone e propriedades.
Abas e dois painéis fazem parte do M4; colunas Miller ficam como alternativa
a validar, não como navegação obrigatória.

Uma pasta física é diferente de uma coleção virtual: rótulos e ícones explícitos.
Arrastar para coleção adiciona referências; arrastar para pasta apresenta a ação
de arquivo com destino claro. Ordenação manual aplica-se a coleções e quadros,
não renomeia arquivos para impor uma ordem no disco.

Atalhos iniciais: Ctrl+F buscar, Ctrl+A selecionar resultados carregáveis,
Espaço prévia, F2 renomear, Ctrl+C/Ctrl+X/Ctrl+V operações de arquivos,
Delete solicitar envio à Lixeira, Escape sair/cancelar contexto.
Ctrl+A usa seleção por consulta no backend para grandes bibliotecas, não envia
milhares de objetos pelo DOM. Operações em lote apresentam contagem e destinos.

Acessibilidade: foco visível, navegação por teclado, rótulos e estados de seleção,
contraste sobre skins com vídeo/imagem e redução de movimento. Evitar autoplay
de milhares de previews. Miniaturas de arte não herdam filtros visuais da skin.

Compacto: superfície própria com recentes/favoritos, busca e abrir seleção na
janela completa. A indexação não depende de a aba estar montada. Não tentar
comprimir dois painéis completos dentro de 360 px.

## 4. Acervo, identidade e formatos

Escolha inicial: **indexar no lugar**. Cadastrar uma pasta não copia seus arquivos
nem exige mover tudo para uma estrutura proprietária. Adições e mudanças externas
devem aparecer progressivamente. Nenhuma varredura de todos os discos por padrão.

Tags livres (Unicode, nome preservado, identidade separada), cores opcionais,
favoritos, notas e coleções manuais pertencem ao catálogo. Uma imagem pode estar
em várias coleções sem duplicação física. Alterações em lote são transacionais.
Tags automáticas futuras serão sugestões com proveniência, separadas das manuais.

Pasta cadastrada = rootId + caminho autorizado + opções de inclusão/exclusão.
Arquivo = assetId estável + rootId + caminho relativo + revisão.
Separar identidade do caminho para preservar notas quando ele muda.
Usar evento de rename e identidade de arquivo/volume quando disponíveis.
Mudanças ambíguas enquanto o app esteve fechado exigem relocalização; não unir
arquivos só porque têm mesmo nome/tamanho. Hash completo somente quando necessário.
Raiz offline não significa que todos os arquivos foram apagados: manter catálogo
e indicar indisponibilidade. Relocalizar raiz deve oferecer prévia das associações.

M1: PNG, JPEG/JPG, WebP, BMP e GIF para miniatura/prévia estática; primeira imagem
de animações. Validar suporte de decoder no Windows alvo. Arquivo não suportado
continua navegável pelo Explorador. SVG/HTML não são renderizados como conteúdo
ativo na WebView privilegiada. RAW, PSD, vídeo, áudio e animação completa são
adaptadores posteriores com testes próprios e fallback visível.

## 5. Arquitetura e reaproveitamento

Existente: React/TypeScript + C#/WPF/WebView2, ponte tipada, skins, galeria e quadros
em Jogos, scripts/comfy_client.py e infraestrutura de testes.
A galeria de Jogos usa imagens pequenas e limites próprios de personagens/quadros;
não reutilizar sua persistência com base64 para milhares de arquivos.
Reaproveitar padrões visuais e, após avaliar, utilitários de pan/zoom. Não refatorar
Jogos, streaming ou IA como pré-requisito desta feature.

Estrutura proposta, criada gradualmente:

| Caminho | Responsabilidade |
| --- | --- |
| src/Models/Assets/ | DTOs, filtros, estados de jobs e contratos versionados |
| src/Services/Assets/AssetLibraryService.cs | Fachada e ciclo de vida do módulo |
| src/Services/Assets/Storage/ | SQLite, migrações, consultas, backup e revisões |
| src/Services/Assets/Indexing/ | Scan incremental, watchers, reconciliação e identidade |
| src/Services/Assets/Imaging/ | Miniaturas, prévias e limites de decodificação |
| src/Services/Assets/Metadata/ | Leitura de metadados e adaptadores por produtor |
| src/Services/Assets/FileOperations/ | Planejamento, execução, histórico e recuperação de operações |
| src/Interop/AssetResourceHandler.cs | Entrega autorizada de mídia à WebView por ID |
| frontend/src/features/assets/ | Provider, Galeria, Explorador, viewer, filtros e inspetor |
| frontend/src/styles/assets.css | CSS com escopo próprio e tokens de skin |
| scripts/tests/AssetLibraryTests/ | Testes C# isolados |
| frontend/tests/assets-ui.test.mjs | Testes de apresentação |
| frontend/tests/assets-native.test.cjs | Integração WebView2/COM com fixtures isoladas |

Pontos de integração existentes: navigation.ts, AppRoutes.tsx, App.tsx, AppShell/
CompactWorkspace, ApiBridge.cs e webview.d.ts. MainWindow apenas conecta ciclo de
vida e hospedagem de recursos; ApiBridge só despacha.

Proposta de armazenamento: Microsoft.Data.Sqlite compatível com net8.0, versão
fixada após avaliar dependências/licenças e empacotamento. Dados em
Data/assets/library.db, cache reconstruível em Data/assets/cache e backups à parte.
Não introduzir um servidor SQL ou exigir runtime extra no PC dos amigos.
Verificar SQLite nativo no pacote self-contained antes de aprovar a dependência.

Entidades iniciais: Roots, Assets, Tags, AssetTags, Collections, CollectionItems,
SavedQueries, Metadata, IndexJobs, FileOperations e LibrarySettings.
Chaves estrangeiras, índices, migração versionada e escritor serializado.
Busca textual por nome/notas/tags e metadados indexados; avaliar FTS5 no M2,
com teste de disponibilidade e consultas parametrizadas, nunca SQL do usuário.
Paginação estável com desempate por ID e revisão da consulta; sinalizar mudanças
durante a paginação para não perder/duplicar resultados silenciosamente.

Backup consistente pela API de backup ou snapshot com escrita coordenada;
não copiar apenas o .db aberto em WAL. Exportar organização em JSON versionado
para recuperação/interoperabilidade, com remapeamento de raízes.
Imagens originais permanecem fora do banco e do backup do catálogo.
Referência técnica: [backup SQLite](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/backup).

## 6. Contratos previstos da ponte

Convenção: DTOs JSON versionados na ponte atual, nomes e respostas finais definidos
no M0; não criar todos os métodos de uma vez. Identificadores são opacos e validados.

| Operação | Entrada/saída e comportamento |
| --- | --- |
| PickAssetRoot / AddAssetRoot | Diálogo nativo retorna seleção autorizada; cadastro devolve rootId/jobId |
| QueryAssets | Filtro estruturado, escopo pasta/descendentes, ordenação, cursor e limite <= 200 |
| GetAssetDetails | assetId; metadados paginados/limitados, tags, notas e revisão |
| ApplyAssetEdits | IDs ou snapshot de seleção, revisão, operação de tags/favoritos/notas |
| SaveAssetCollection / SaveAssetQuery | Coleção manual ou árvore de filtros validada |
| StartAssetIndex / GetAssetJob / CancelAssetJob | Iniciar retorna jobId imediatamente; progresso e cancelamento |
| PlanAssetFileOperation | Tipo, seleção, destino autorizado; retorna plano, conflitos e revisões |
| ExecuteAssetFileOperation | planId validado; revalida origem/destino e inicia job rastreável |
| UndoAssetFileOperation | operationId; verifica pré-condições e explica indisponibilidade |
| RelinkAssetRoot / RelinkAsset | Prévia de correspondências antes de aplicar |
| RevealAssetInExplorer | ID autorizado; abre localização com argumento seguro |
| GetAssetMediaUrl | ID + revisão + variante; URL restrita à interface do app |

Pesquisa/consultas demoradas também precisam de cancelamento e resultados antigos
descartados por requestId. Nada de scan, hash ou decodificação na thread WPF/COM.
Jobs mantêm progresso e erros por item; polling de status limitado (ex.: 500 ms)
ou canal tipado existente, sem push de um callback por miniatura/frame.

## 7. Indexação, segurança e consumo

Enumerar metadados baratos primeiro; detalhes, hashes, paletas e thumbnails depois.
Fila limitada, prioridade aos itens visíveis e pequeno prefetch, cancelamento ao
trocar de pasta e deduplicação de tarefas pela revisão do arquivo.
FileSystemWatcher é sinal de mudança, não a fonte única da verdade: coalescer
eventos, reconciliar no startup, no overflow e sob pedido; tentar de novo arquivos
ainda sendo escritos pelo ComfyUI. Não marcar scan incompleto como remoção.
[Limite de buffer do watcher](https://learn.microsoft.com/en-us/dotnet/api/system.io.internalbufferoverflowexception?view=net-8.0).

Começar com 1 worker de imagens, permitir até 2 após medição; não disputar toda
a CPU/VRAM com jogos, transmissões ou IA. Meta inicial de cache de thumbnails
em RAM: 128 MiB; disco: 1 GiB configurável/LRU. Esses são limites do cache,
não limites garantidos da memória total do processo/decoders.
Pausa manual e redução de trabalho sob pressão; retomar sem refazer tudo.

Virtualizar a grade/lista e limitar DOM/decoders aos itens próximos da tela.
Liberar URLs/texturas/bitmaps não utilizados. A comparação limita originais
simultâneos; imagens gigantes recebem preview reduzido e aviso.
Instrumentar tempo de consulta, primeira grade útil, frames longos e uso de memória.
60 FPS é meta de interação com cache quente; 120 Hz é melhoria para hardware
compatível. Não prometer 60/120 FPS apenas porque o cache é assíncrono.

Mídia local não deve ser servida por uma rota HTTP que aceita qualquer caminho.
Resolver assetId somente em raízes autorizadas, verificar caminho final/reparse
points e acesso no momento da abertura. Por padrão, não seguir junctions/symlinks.
Reutilizar a política de navegação do app; a ponte não fica acessível a páginas externas.
Tamanho de arquivo, quantidade de pixels, metadados descomprimidos e profundidade
JSON precisam de limites, testados com entradas malformadas.
Metadados são dados inertes: não executar workflow, shell, URLs ou instruções lidas
de uma imagem. Não carregar previews remotos automaticamente.

## 8. Operações de arquivos com preservação de dados

Organização física é parte do escopo, mas não acontece implicitamente ao cadastrar
pastas ou editar tags. Oferecer ações explícitas: criar pasta, renomear, copiar,
mover e enviar à Lixeira. Remover da coleção/catálogo não apaga o original.

Antes de executar, planejar origens, destinos, quantidade, espaço necessário,
conflitos e itens indisponíveis. Não sobrescrever em silêncio.
Primeira implementação resolve colisões por ignorar ou gerar novo nome; a opção
de substituir exige fluxo explícito e cobertura adicional antes de ser habilitada.

No mesmo volume, preferir operação nativa de rename/move quando aplicável.
Entre volumes, copiar para destino temporário, validar conclusão/conteúdo,
finalizar destino e só então retirar origem conforme o plano. Cancelar ou falhar
na cópia não pode apagar a origem. Preservar metadados do catálogo por assetId;
copy cria nova identidade, move preserva a existente.

Banco e filesystem não possuem transação conjunta: diário de intenção e resultado
por item, estados pending/running/completed/failed/interrupted e reconciliação após
crash. Nunca repetir operações destrutivas automaticamente após reiniciar.
Undo somente quando as pré-condições ainda valem; usar a Lixeira do Windows para
exclusão recuperável e explicar quando a restauração não está disponível.
Testar arquivo em uso, permissões, nomes inválidos, disco cheio, cross-volume,
renomeação só de caixa, pastas ancestrais e alterações externas concorrentes.

## 9. Metadados de geração e coleções inteligentes

M3: PNG produzido pelo ComfyUI e formato textual de geração reconhecido,
com fixtures reais/sintéticas. Ler prompt/workflow e parâmetros disponíveis,
preservando produtor, versão do parser e origem do campo.
Um workflow pode ter vários samplers, modelos e prompts: exibir múltiplas etapas
ou manter o grafo bruto; não inventar um único seed/steps/modelo universal.
WEBP/JPEG/EXIF/XMP entram por adaptador validado; não assumir que todo arquivo
dessas extensões contém prompt. Mostrar ausente, não suportado e falha separadamente.
Valor ausente nunca vira zero; texto editado manualmente fica separado do extraído.
Metadados completos carregam apenas no inspetor, não em cada card.

Pastas inteligentes são consultas salvas versionadas, com ALL/ANY/NOT e predicados
sobre tags, tipo, datas, dimensões, proporção, favoritos e campos extraídos.
Exemplo: tag Personagem X + largura >= 1920 + favorito.
Exibir quantos itens correspondem e se subpastas entram. Não mover arquivos
quando uma consulta muda.

## 10. Marcos e entregas verificáveis

| Marco | Trabalho | Critério de saída |
| --- | --- | --- |
| M0 — Contrato e protótipo | Wireframes de Galeria e Explorador, catálogo sintético, estado compartilhado, formatos/limites e decisões de UX | Alternar duas visões mantém pasta/seleção/filtro; feedback registrado na matriz |
| M1 — Acervo navegável | SQLite/migrações, raízes, scan, watcher/reconciliação, mídia autorizada, miniaturas, grade e lista, viewer | Navegar por pasta grande antes do fim do scan; reinício, offline e inválidos tratados sem modificar originais |
| M2 — Organização lógica | Tags livres/em lote, favoritos, notas, coleções, busca, ordenação e backup/exportação | Organização persiste após reinício; arquivo pode pertencer a várias coleções; backup restaurável |
| M3 — Artes e comparação | Metadados PNG de geração, inspetor, comparação e consultas inteligentes | Buscar fixtures por metadados, lidar com campos ausentes e comparar variações sem bloquear UI |
| M4 — Explorador completo inicial | Abas, dois painéis, criar/renomear/copiar/mover/Lixeira, diário/recuperação/undo possível, compacto | Fluxos Galeria + Explorador concluídos, falhas de I/O preservam dados, regressões e pacote aprovados |
| M5 — Personalização visual | Canvas de referências, paletas/busca por cor, layouts salvos, prévias animadas controladas e colunas opcionais | Escolhas guiadas pelos testes do usuário, memória/latência medidas |
| M6 — Integrações | Usar mídia em skins/Jogos, ComfyUI para gerar/importar/reutilizar com autorização, sugestões de tags por IA, adaptador Everything opcional | Contratos explícitos, orçamento de recursos, proveniência e autorização; biblioteca continua utilizável sem esses motores |

M0–M4 formam o compromisso inicial de produto. A ordem permite testar partes úteis
sem abandonar a visão completa. Não instalar Everything, codecs, modelos ou
serviços externos como dependências obrigatórias sem uma decisão documentada.
MFT/USN direto, plugin de shell e substituir o Explorer do Windows ficam fora desta
primeira entrega. O ganho deve ser demonstrado antes de ampliar privilégios/escopo.

## 11. Validação e critérios de pronto

Fixtures isoladas: 100/1.000/10.000 arquivos, formatos mistos, Unicode, repetidos,
PNG com e sem metadados, imagem corrompida/gigante, escrita parcial e pasta offline.
Nenhum teste move, apaga ou etiqueta imagens pessoais do usuário.

Testes C#: consultas/paginação/revisões, migração/backup, tags Unicode, regras de
busca, cancelamento, overflow/reconciliação, rename/relink, limites dos parsers,
path traversal/reparse points e operações de arquivos com falhas injetadas.
Frontend: seleção/teclado, persistência entre vistas, filtros, inspector,
comparação, estados vazios, alto contraste, skins extremas e compacto.
Integração nativa: diálogos e ponte COM, entrega de mídia, filesystem real isolado,
reinício, viewer e Windows Lixeira quando disponível em ambiente de teste.

Orçamentos iniciais de aceitação no PC de referência, a medir e ajustar:
- Busca indexada em 10.000 itens: p95 <= 200 ms para primeira página, sem scan.
- Primeira grade útil com cache quente: <= 1 s; fria mostra placeholders/progresso.
- Rolagem visa frames de 16,7 ms em 60 Hz; registrar p95/p99 e pausas > 50 ms.
- Cache respeita o limite configurado e memória volta a patamar estável após navegar.
São metas de benchmark local, não promessa para qualquer disco ou carga.

Para cada marco: testes relevantes + build quando houver código + test_ci.ps1,
registro em AGENT_CONTEXT.md e resumo do que foi realmente medido.
Para distribuição: package_release.ps1, SQLite nativo validado, assets íntegros,
Data/assets/cache/raízes/catálogo privados ausentes do pacote e migração preservada.
Não incrementar versão, commitar, publicar ou substituir o app durante esta etapa
de planejamento.

## 12. Próximas tarefas após a implementação inicial

O núcleo M0–M3 e grande parte de M4 já estão implementados. Antes de considerar M4
completo, validar com bibliotecas reais e fechar as diferenças enumeradas no guia
de uso: grade virtualizada, seleção por consulta, atalhos de copiar/colar, restauração
de itens da Lixeira na própria interface, movimentação segura de pastas entre
volumes e testes de falha de E/S. M5–M6 continuam como expansão do produto.

Decisões abertas para testar, sem bloquear as melhorias: densidade
preferida, recorte/contain, abrir por duplo clique ou Espaço, hover preview,
árvore versus colunas, disposição da comparação, posição do inspetor e regras
de arrastar. A decisão já confirmada é manter **Galeria e Explorador**.
