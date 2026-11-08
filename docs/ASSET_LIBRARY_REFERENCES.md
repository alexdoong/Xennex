# Referências e decisões de experiência — Biblioteca Xennex

Pesquisa inicial em 28/09/2026. Complementa
[ASSET_LIBRARY_PLAN.md](ASSET_LIBRARY_PLAN.md).
Status: características verificadas em documentação de produto; preferências
do usuário serão registradas após experimentação. Nenhum aplicativo externo
foi instalado ou testado visualmente nesta pesquisa.

## Referências verificadas e aplicação proposta

| Referência | Recurso confirmado / inspiração | Aplicação no Xennex e cuidado |
| --- | --- | --- |
| [Everything — FAQ](https://www.voidtools.com/faq/) | Busca por nomes e atualização do índice NTFS via USN | Resultados progressivos e baixo trabalho redundante. Indexação NTFS requer serviço/privilégio; velocidade de nomes não representa geração de thumbnails ou busca de prompts |
| [Listary — Quick Switch](https://www.listary.com/) | Busca acessível no fluxo de arquivos e troca rápida de localização | Busca interna por teclado e favoritos; integração global com diálogos fica para depois |
| [Eagle — suporte](https://en.eagle.cool/support/desktop) | Tags, pastas inteligentes e busca por cor | Inspetor, filtros visuais e coleções; validar o custo de gerar paletas antes de indexar tudo |
| [Billfish — modos de importação](https://www.billfish.cn/help/daorumoshiqubie) | Oferece copiar, mover e indexar arquivos em seu lugar | Não é correto descrevê-lo como exclusivamente baseado em pastas sem cópia. Nossa escolha inicial é indexar no lugar, com operações físicas explícitas |
| [Billfish — arquivos indexados](https://www.billfish.cn/help/suoyinsucai) | Referências externas podem ficar ausentes após mudanças de caminho | Planejar offline, identidade estável, reconciliação e relocalização desde o início |
| [PureRef — canvas](https://www.pureref.com/handbook/canvas/) | Canvas expansível, pan/zoom, alinhamento e bloqueio | Quadro de referências no M5; imagens por referência ao assetId, sem copiar originais para cada quadro |
| [Files — dois painéis](https://www.files.community/docs/features/dual-pane) / [tags](https://www.files.community/docs/features/tags) | Navegação simultânea e identificação por tags | Dois painéis no Explorador, com destino e conflitos claros; separá-los da comparação de imagens |
| [OneCommander — colunas](https://onecommander.com/help2/FolderColumnsandNavigationPane.html) | Colunas para percorrer hierarquias | Alternativa à árvore, validada com o usuário em pastas profundas; evitar ocupar toda a área das artes |

Não adotamos como fatos os rótulos “padrão da indústria”, “melhor ferramenta” ou
“consumo mínimo” sem benchmark/amostra. Hover scrubbing, prévias animadas e busca
por similaridade são propostas a avaliar, não recursos de terceiros já comprovados
por esta pesquisa nem compromissos de desempenho.

## O que sabemos sobre preferências

Confirmado pelo usuário: quer galeria de artes completa **e** possibilidade de
organizar os arquivos, alternando entre as duas experiências. Não quer limitar
a ferramenta a uma única apresentação.

Ainda não há pesquisa de satisfação representativa. Resultados de busca apontaram
discussões individuais sobre hierarquias e escopo de subpastas no Eagle, mas as
páginas completas não puderam ser recuperadas nesta sessão; não fundamentar uma
decisão ou afirmar consenso com esses trechos.

Próxima rodada de pesquisa: recolher exemplos verificáveis de uso e relatos de
comunidade por tema. Registrar URL, data/versão, tarefa, preferência/queixa,
solução sugerida e se conseguimos reproduzir. Separar relato de usuário,
descrição do fabricante, benchmark próprio e hipótese nossa.
Não exigir compras/instalações para começar: documentação e protótipos locais
permitem avaliar o fluxo; testes dos aplicativos são opcionais.

## Matriz viva de avaliação

| Tema | Alternativas para testar | Decisão inicial | Feedback do usuário |
| --- | --- | --- | --- |
| Visualização | Galeria / Explorador | Ambas, mesmo acervo e estado | Confirmado |
| Miniaturas | Proporção original / recorte uniforme | Original, com alternância | Pendente |
| Densidade | Grande / confortável / compacta | Controle de tamanho | Pendente |
| Prévia | Duplo clique / Espaço / hover | Duplo clique e Espaço; hover opcional | Pendente |
| Navegação | Árvore / breadcrumbs / colunas | Árvore + breadcrumbs; colunas posteriores | Pendente |
| Organização | Tags / coleções / pastas físicas | Três conceitos distintos e visíveis | Pendente |
| Arrastar | Referenciar em coleção / copiar / mover | Destino e ação explícitos | Pendente |
| Comparar | 2–4 imagens / slider A-B / zoom sincronizado | Lado a lado, sincronização opcional | Pendente |
| Animações | Automáticas / sob demanda / desligadas | Sob demanda | Pendente |
| Inspetor | Lateral / modal / recolhido | Lateral recolhível | Pendente |
| Canvas | Layout livre / alinhado / colagem | M5; começar com pan/zoom e alinhamento | Pendente |
| Aparência | Skin global / fundo neutro para artes | Moldura da skin; área da arte neutra | Pendente |

Para cada rodada, pedir exemplos concretos do que agradou/incomodou e registrar
uma decisão pequena. Não transformar toda preferência em uma configuração:
manter bons padrões e só expor alternativas úteis.

## Roteiro para o primeiro protótipo

1. Abrir pasta mista, olhar as artes na Galeria e localizar o mesmo item na lista.
2. Selecionar 30 itens, aplicar tags e adicionar a duas coleções sem duplicá-los.
3. Buscar favoritas por tag + dimensão; verificar se inclui subpastas.
4. Comparar três variações, ler os prompts disponíveis e voltar mantendo seleção.
5. Organizar arquivos entre duas pastas, entendendo antes o que será copiado/movido.
6. Desconectar/remover uma raiz de teste e relocalizar sem perder tags/notas.
7. Repetir com skin de fundo animado, janela pequena e modo compacto.

Usar imagens de teste/autorizadas. Medir tempo até encontrar um item, quantidade
de passos, enganos de seleção/operação e interrupções da interface.
A melhor escolha é a que funciona no fluxo do usuário, não a que acumula mais
recursos da lista de referências.
