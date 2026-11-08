# Skins: edição durante o uso

Abra o ícone de paleta na barra lateral ou **Configurações → Editar Skin**.
O painel fica aberto ao trocar de aba e pode ser recolhido. A prévia é imediata;
**Salvar e aplicar** persiste as alterações. Fechar com alterações oferece salvar,
continuar ou descartar. Descartar restaura a última skin salva, inclusive após
salvar uma cópia durante a mesma edição.

## Controles

- Fundo: imagem, vídeo MP4/WebM, cor ou degradê; enquadramento, posição, brilho,
  saturação, opacidade, desfoque e sobreposição.
- Cores: principal/hover, texto, texto secundário, botões e campos; quatro paletas.
- Painéis: cor, opacidade, blur, cantos, espaço interno, sombras e bordas.
- Cartões: cor e opacidade do fundo, cor e opacidade da borda, cantos, espaço
  interno e distância entre cartões. A prévia se aplica aos cartões comuns e
  aos blocos de Configurações.
- Barras: cores, imagens, opacidade das imagens, largura lateral, cantos e blur.
- Layout: escala de 80 a 130%, margens, fonte e rolagem. Redução de movimento
  desativa animações CSS e pausa vídeo de fundo; não interrompe transmissões.
- Estrutura: navegação à esquerda, direita ou embaixo; controles da janela à
  esquerda, centro ou direita; janela flutuante ou preenchida; acabamento em
  vidro, Liquid Glass, sólido, terminal ou ornamentado. A ordem dos atalhos das áreas
  principais pode ser alterada; Configurações permanece acessível no fim.
  Os quatro blocos de Configurações podem ser reordenados com as setas e
  exibidos em uma ou duas colunas. Em janelas até 1100 px, as duas colunas
  se recolhem automaticamente para manter os controles legíveis.
- Presets Liquid Moon, Gryphlink, Merlin, Terminal e Retro 15 KB oferecem conjuntos iniciais
  de layout e cores. Cada campo continua editável depois de escolher um preset.
- Busca de ajustes, desfazer/refazer (até 50 alterações) e restauração visual.
  Alguns componentes têm espaçamento ou cores semânticas próprios; os controles
  de skin abrangem as superfícies comuns, sem alterar cores de erro/status.

A skin **default** permanece como base de distribuição. Salvar a edição dela cria
uma cópia pessoal; crie/salve essa cópia antes de importar mídia do computador.
Não é necessário recompilar o aplicativo para editar uma skin.
O modo compacto mantém seu posicionamento físico próprio. As escolhas de
navegação e controles da janela cheia não alteram o recolhimento do compacto;
cores e acabamento continuam se aplicando à interface.

## Liquid Glass / Liquid Moon

Em **Estrutura → Estilos prontos**, escolha **Liquid Moon** para aplicar a
paleta azul noturna, bordas de tom dourado suave, cantos arredondados e vidro
translúcido. O preset usa degradê como fundo inicial; depois escolha sua própria
imagem/vídeo em **Fundo**. A skin ativa só muda permanentemente ao salvar.
Também é possível selecionar somente **Acabamento → Liquid Glass** para
manter as cores, mídia e layout da sua skin atual.

Em **Painéis**, ajuste **Reflexos do Liquid Glass** (0–1), opacidade, desfoque,
bordas e sombras. O reflexo segue a cor da borda; zero remove a iluminação do
acabamento. Cores semânticas de erro/status e superfícies de vídeo/prévia não
recebem esse tratamento. O editor usa uma paleta própria para manter leitura.

O efeito é vidro estilizado em CSS dentro do conteúdo WebView2. Não faz
refração física nem desfoque do desktop atrás da janela. Reflexos são estáticos;
não há animação contínua nem filtro SVG de deslocamento. O desfoque fica nos
painéis grandes, sem outra camada por miniatura, linha ou cartão interno.
O compacto usa o mesmo acabamento sem blur adicional e mantém docking/animação
sob controle do serviço nativo. Reduzir movimento continua sendo respeitado.

Revisão de organização em 04/10/2026: contratos/defaults/validação continuam
sincronizados em C#/TypeScript; `skin-theme.css` aplica tokens, `skin-layout.css`
cuida da geometria e `skin-surfaces.css` concentra acabamentos. Esse último é
importado após o layout e antes dos ajustes físicos do compacto. Os estilos
de módulos permanecem nos próprios arquivos; as cores fixas de Biblioteca e
painéis de sala recebem os tokens apenas quando o acabamento Liquid Glass
está ativo. A revisão não altera skins existentes nem todos os estilos legados.

## Persistência e compatibilidade

SkinRepository normaliza JSON camelCase/PascalCase, completa propriedades novas,
preserva campos desconhecidos, limita números e grava por substituição do arquivo
completo. Nomes inválidos, pastas com links e nomes já existentes são recusados.
Duplicar copia as mídias locais referenciadas para a nova pasta e reescreve URLs;
a cópia não depende dos arquivos da skin original. URLs remotas continuam remotas.
PNG/JPG/JPEG/WebP/GIF/BMP e MP4/WebM: máximo de 512 MiB por arquivo.

Arquivos importados ficam em wwwroot/skins/<nome>/assets. Descartar a prévia não
apaga mídias já importadas: podem ser reutilizadas, e não há limpeza automática
que arrisque apagar arquivos em uso. A importação não transcodifica vídeos.

As atualizações preservam skins pessoais. O pacote distribui apenas default.
SkinService cuida de diálogo/ativação, SkinRepository dos arquivos, useAppState
separa skin salva de prévia, SkinBackground aplica a mídia e SkinEditorModal
monta o painel por portal fora do conteúdo escalonado.

## Validação

- dotnet run --project scripts/tests/SkinTests/SkinTests.csproj
- npm run build (em frontend)
- dotnet build Xennex.csproj -c Release -o bin/LocalAiDev
- powershell -ExecutionPolicy Bypass -File scripts/tests/test_skins_native.ps1

O teste nativo usa dados isolados em bin, WebView2/COM, imagens em bin/skins-ui e
duas inicializações. Exercita prévia, desfazer/refazer, navegação, descarte,
salvamento/cópia, colisão de nomes e persistência, inclusive o acabamento Liquid
Glass e a intensidade dos reflexos. `compact-ui.test.mjs` também verifica
Liquid Moon na janela cheia/Biblioteca/salas/compacto e a troca de acabamento.
Na segunda inicialização a
ativação dos botões é feita pelo DOM porque a janela WPF oculta pode descartar
eventos de entrada injetados enquanto não tem foco. Requer Playwright instalado
(ou PLAYWRIGHT_MODULE configurado) e nenhuma outra instância Xennex aberta.
