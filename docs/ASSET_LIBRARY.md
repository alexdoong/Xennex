# Biblioteca de artes — uso e estado atual

Atualizado em 01/10/2026. A aba **Biblioteca** junta duas visões do mesmo acervo local: **Galeria** para olhar as artes e **Explorador** para organizar arquivos e pastas. O plano de produto e as referências estão em [ASSET_LIBRARY_PLAN.md](ASSET_LIBRARY_PLAN.md) e [ASSET_LIBRARY_REFERENCES.md](ASSET_LIBRARY_REFERENCES.md).

## Primeiros passos

**Abrir no VR** oferece Biblioteca completa (padrão), com galeria, explorador,
acervos e subpastas navegáveis no headset, em páginas de 12 entradas. Seleção
atual continua disponível para abrir somente as imagens escolhidas. O painel
SteamVR inclui zoom, fixação, recentralização e ajuste de tamanho/distância.
A janela pode ficar na bandeja enquanto você usa o headset. Consulte
[VR.md](VR.md) para uso, pré-requisitos e os limites da navegação/espelhamento.

Abra Biblioteca e use **Escolher pasta**. O Xennex indexa a pasta escolhida no lugar; não copia os originais. É possível cadastrar mais de uma pasta, inclusive uma saída do ComfyUI. Os registros e as miniaturas ficam em `Data/assets/` do executável em uso. Nunca inclua essa pasta em pacotes de release ou no Git. A indexação roda em segundo plano, pode ser pausada/cancelada e reage a mudanças externas com nova varredura da raiz. O catálogo é SQLite; **Backup do catálogo** escolhe um destino para uma cópia consistente. Este backup não inclui os arquivos de arte originais.

**Expandir área** recolhe o cabeçalho da Biblioteca e desloca o explorador para cima; **Mostrar cabeçalho** restaura a apresentação. O botão `+` ao lado de **Pastas** continua disponível nos dois estados. Se surgir o aviso de que a interface está mais recente que o executável, feche a instância antiga e abra um build atualizado: o código `0x80020006` indica que a ponte nativa aberta não reconhece o método da Biblioteca.

Use **Galeria** para percorrer imagens em páginas de até 100 itens, ajustar tamanho/recorte das miniaturas, abrir o visualizador e comparar de 2 a 4 imagens com zoom independente ou sincronizado. Use **Explorador** para ver outros tipos de arquivo e pastas, abrir abas e um segundo painel, criar pasta, renomear, copiar, mover ou enviar à Lixeira. Operações físicas sempre mostram uma prévia de origem/destino, pedem confirmação e registram o resultado. Nomes ocupados podem ser resolvidos por arquivo, renomeados automaticamente ou ignorados; nenhum arquivo existente é sobrescrito. O histórico oferece **Desfazer** somente para renomeações e movimentos de arquivos na mesma unidade quando o arquivo ainda não mudou.

Em **Mover** e **Copiar**, escolha visualmente uma pasta cadastrada e navegue pelas subpastas. O caminho escolhido aparece antes da prévia; o botão **Voltar** e as partes clicáveis do caminho permitem retornar. A lista mostra apenas pastas, em páginas de até 200, com filtro entre as pastas já carregadas. O destino ainda é validado pelo serviço nativo no momento da prévia.

Em **Renomear**, **Mover** ou **Copiar**, ative **Usar padrão de numeração** para aplicar uma regra ao lote inteiro ou somente aos nomes em conflito. Informe um **Nome base**, como `denia`, e um **Padrão**, como `{base}{number}` ou `{base}_{number}`. O campo **Dígitos** permite nomes como `denia_001.png`; cada extensão original é preservada. **Continuar após o maior número existente no destino** considera nomes compatíveis com o mesmo padrão, em qualquer extensão, na pasta de destino imediata: se já há `denia_022.jpg`, o próximo será `denia_023.png`. Desmarque para informar o número inicial, inclusive zero. Ao renomear arquivos de várias pastas, a sequência é única e começa após o maior número encontrado entre essas pastas. Os padrões são declarativos; não aceitam código ou expressões.

Abra **Escolher ordem e nomes** para ordenar por nome, data ou ordem da seleção, ou reorganizar as miniaturas pelas alças e setas. A numeração segue essa lista. Cada item pode usar a regra, receber um nome específico completo (incluindo extensão) ou ser ignorado. Ignorar deixa o original onde está e não consome um número. **Ver prévia** aponta os conflitos com o disco e entre arquivos do próprio lote; escolha outro nome, aplique numeração ou ignore os itens antes de confirmar. **Renomear automaticamente os conflitos** acrescenta sufixos como `(2)`. Alterar a ordem, o destino ou a regra exige **Atualizar prévia**. Prévia e confirmação não substituem arquivos já existentes; o serviço revalida todas as origens/destinos antes de iniciar e cada item durante a execução.

**Busca rápida** (Ctrl+K) abre o Explorador em todos os acervos cadastrados e foca o campo de pesquisa. A busca usa o catálogo do Xennex, é acionada após uma breve pausa de digitação e mostra o caminho de cada resultado. Ela não varre discos não cadastrados nem usa o índice MFT do Everything; uma análise de espaço no estilo WizTree ainda não faz parte desta versão.

No visualizador, as setas de imagem ficam juntas em uma barra central inferior, fora da borda que revela a navegação do aplicativo; as teclas de seta também navegam. Em **Dois painéis**, escolha disposição lado a lado ou empilhada e ajuste a proporção do painel principal de 25% a 75%. **Fechar este painel** promove a pasta do segundo painel ao principal; o botão de fechar no segundo mantém o principal. A disposição e a proporção são lembradas nesta WebView.

Na Galeria ou no Explorador, use **Selecionar vários** para marcar itens com cliques simples, **Selecionar página** para marcar os até 100 itens visíveis, Ctrl+clique para alternar um item ou Shift+clique para selecionar um intervalo. **Limpar seleção** desfaz a marcação. Com 2 a 100 itens, **Editar itens** ou o clique direito abre a edição conjunta de favoritos, tags e coleções; essa edição é atômica no catálogo e não altera os arquivos originais. O clique direito também oferece copiar, mover, renomear um ou vários itens e enviar à Lixeira; operações físicas exibem prévia e confirmação. Para criar uma coleção nova, use primeiro o campo da barra lateral.

Favoritos, tags livres, notas e coleções pertencem ao catálogo e não modificam o conteúdo dos arquivos. Os filtros avançados permitem regras ALL/ANY/NOT por nome, notas, metadados, tags, tamanho e dimensões; é possível salvar a consulta. O inspetor mostra dimensões e texto de geração extraído de PNG quando presente. Para PNGs do ComfyUI, selecione a imagem e veja o resumo de checkpoint, LoRAs, prompts e parâmetros do sampler em **Dados da imagem**; use **Ver geração e nodes → Texto original** para ler o JSON completo. O arquivo não é alterado. Esses campos podem ser editados por terceiros e não provam a origem da imagem. Quando uma raiz fica offline, os registros continuam no catálogo. **Relocalizar** mostra quantas entradas do caminho relativo foram encontradas antes de confirmar. A superfície compacta fornece acesso rápido à Biblioteca.

**Ver geração e nodes** abre uma janela com mapa de nodes e conexões, parâmetros resumidos e texto original. O mapa usa o grafo de execução `prompt` quando disponível e o `workflow` salvo como alternativa. É uma visualização somente de leitura: não executa nodes nem importa o fluxo para o ComfyUI. Conexões e títulos vêm dos metadados, portanto uma imagem sem esses campos não oferece um fluxo reconstruível. O resumo coloca prompts positivo e negativo em evidência.

**Todas as tags** abre uma visão pesquisável e paginada de etiquetas manuais e termos extraídos dos prompts. As abas **Juntas**, **Manuais**, **Prompt positivo** e **Prompt negativo** mostram a origem separadamente; cada termo ou marcador de origem pode filtrar a galeria. O número ao lado de cada origem conta imagens associadas naquela origem. O Xennex extrai termos separados por vírgula ou linha, remove pesos numéricos simples e guarda essa classificação em `Data/assets/library.db`; os arquivos de imagem não mudam. Isso é uma heurística para prompts de ComfyUI ligados diretamente ao sampler, campos `positive`/`negative` e texto `parameters`. Prompts de nodes personalizados, referências indiretas ou frases com vírgulas literais podem produzir termos incompletos ou imprecisos. **Prompt negativo** não significa que a imagem foi avaliada como ruim; uma classificação pessoal de resultados bons/ruins é uma evolução futura separada.

**Com metadados** filtra a Galeria para mostrar somente imagens em que a indexação encontrou texto PNG. O selo **META** identifica essas imagens na Galeria e no Explorador, sem carregar o JSON completo para cada cartão. O filtro usa o catálogo local; não reabre os arquivos a cada consulta. Na primeira indexação ou quando tamanho/data de modificação mudam, o serviço precisa examinar cada PNG para descobrir seus metadados. Revarreduras de arquivos inalterados reaproveitam o texto já guardado no banco, sem lê-lo novamente do disco nem transferi-lo inteiro em cada busca. Metadados de outros formatos e EXIF ainda não são classificados por esse indicador.

## Limites desta versão

- A grade usa paginação e carregamento preguiçoso de imagens; ainda não há virtualização contínua nem seleção por consulta sobre milhares de resultados. Ctrl+A seleciona somente a página carregada (até 100 itens).
- O índice usa varredura de pastas cadastradas e observação por FileSystemWatcher. Não usa MFT/USN nem substitui Everything. Mudanças externas podem exigir **Atualizar índice**; roots muito grandes podem ter custo de revarredura.
- PNG/JPEG/WebP/BMP/GIF têm prévia estática se o decoder do Windows conseguir ler o arquivo. O extrator de parâmetros de geração lê texto de PNG; outros formatos têm dimensão básica, sem promessa de extrair prompts. GIF animado mostra quadro estático. A primeira abertura de **Todas as tags** pode levar mais tempo em um acervo antigo: ela preenche um índice derivado em lotes de até 24 imagens; chamadas seguintes reutilizam o índice enquanto os metadados não mudarem.
- Ações em lote estão limitadas a 100 itens; mover uma pasta entre unidades é recusado para preservar a origem. Envio à Lixeira usa a Lixeira do Windows; restauração deve ser feita pelo Windows. Não há ainda Ctrl+C/Ctrl+V próprio da Biblioteca.
- A numeração aplica-se a arquivos, com até nove dígitos e valor máximo de 999999999. Renomeações cíclicas (trocar `a.png` por `b.png` e vice-versa) não são executadas: os destinos ocupados precisam de outros nomes. Operações físicas são registradas por arquivo, não formam uma transação única; uma falha ou cancelamento durante a execução pode deixar parte do lote concluída. Consulte o histórico para verificar ou desfazer os itens elegíveis.
- Não há neste módulo canvas infinito, busca por cor, prévia animada, acoplamento à geração ComfyUI, integração automática com skins/Jogos, sugestões de tags por IA ou adaptador Everything. Essas opções seguem no plano M5–M6.
- A seleção, localização e modo são lembrados na WebView deste executável. Os dados de catálogo do build de desenvolvimento são separados dos `Data/` do app instalado na pasta principal.

## Arquitetura e segurança

`src/Services/Assets/` mantém índice, catálogo SQLite, miniaturas e operações; `src/Models/Assets/` define contratos; `src/Interop/AssetResourceHandler.cs` serve miniaturas/prévias a partir de IDs opacos. O frontend fica em `frontend/src/features/assets/` e `frontend/src/styles/assets.css`. A ponte COM está tipada em `frontend/src/webview.d.ts`. O handler de mídia usa host próprio não mapeado para que o interceptador WebView2 possa aplicar a verificação de ID e de caminho. Diretórios reparse e saídas fora das pastas autorizadas são rejeitados. Não abrir HTML/SVG de origem dentro da WebView privilegiada.

## Como validar

```powershell
cd frontend
npm run build
npm run lint
node tests/assets-ui.test.mjs
cd ..
dotnet run --project scripts/tests/AssetLibraryTests/AssetLibraryTests.csproj -c Release
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_ci.ps1
```

O teste nativo abaixo abre uma cópia isolada do Xennex, usa WebView2 real, ponte COM, SQLite, miniatura e reinício. Feche a instância principal e deixe a porta de depuração 9232 livre:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_assets_native.ps1
```

Para um benchmark sintético de 10 mil entradas: `dotnet run --project scripts/tests/AssetLibraryTests/AssetLibraryTests.csproj -c Release -- --benchmark`. Ele não substitui medições com o acervo real do usuário.

Em 28/09/2026, essa fixture local de 10 mil entradas levou 9,55 s para indexar; 50 buscas tiveram p95 de 4,5 ms e o processo usou 66 MiB de memória privada ao fim da medição. O teste WebView2 nativo confirmou escrita e leitura após reinício. O lint do frontend terminou com avisos preexistentes de outras áreas, sem avisos da Biblioteca. Esses números não medem a fluidez da grade com milhares de imagens reais. Os testes de catálogo e UI agora cobrem também a edição em lote de duas imagens, associação à coleção, rollback de lote inválido, reorganização e fechamento dos dois painéis e a navegação do visualizador.

No teste manual, escolha uma pasta descartável primeiro; alterne Galeria/Explorador, filtre, compare, crie coleções e experimente operações de arquivos com a prévia. Só depois adicione a coleção principal de artes. Preserve um backup independente dos originais para qualquer gerenciamento físico.
