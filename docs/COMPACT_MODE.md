# Painel compacto

Atualizado em 27/09/2026. O painel tem 360 × até 680 DIPs e interfaces próprias
para IA, jogos, transmissões, Gestures, Cloud, configurações e aparência.
Os controllers são compartilhados com a janela completa. Entrar/sair do
compacto não deve criar outra sala, captura ou execução de IA.

## Posição e recolhimento

Posição aberta e direção de recolhimento são preferências independentes.
Ajustar posição permite distância da lateral (0–2000 DIPs) e altura (0–100%
do espaço livre), sempre limitadas ao monitor atual.

- Automático escolhe a borda real mais próxima entre cima, esquerda e direita.
  O preset desempata distâncias iguais. Não há recolhimento inferior.
- Cima/Esquerda/Direita permitem escolher a direção explicitamente.
- A alça termina na borda física da área de trabalho, mantendo o deslocamento
  no outro eixo. Uma posição aberta afastada não deixa uma alça flutuante.
- O viewport encolhe até 16 DIPs dentro do próprio monitor; nada deve invadir
  o monitor vizinho. O canvas React mantém largura E altura durante a animação.
- CompactMotion interpola por tempo (até 240 ms) com aceleração/desaceleração.
  Inverter a direção parte da posição atual. A preferência de animações do
  Windows é respeitada.
- FPS da animação fica em Ajustar posição: Automático (padrão), 30, 60 ou 120.
  A escolha é salva em SidebarAnimationFps. É um limite, não garantia de FPS.
  Automático acompanha os callbacks de renderização disponíveis.
- Após sair do painel, há 650 ms de tolerância; entrar no modo dá uma margem extra.
  O gatilho da alça permanece estável durante o movimento.
- Fixar mantém aberto. Digitação, seleção e arraste mantêm uma interação
  temporária; trocar de área ou perder foco libera esse bloqueio.
- Expandir restaura posição, tamanho mínimo, maximização e Topmost anteriores.

SidebarService agenda os frames em CompositionTarget.Rendering, com deduplicação
por RenderingTime. CompactFrameCadence limita quadros sem acumular atrasados.
O timer de 50 ms apenas detecta hover/estado parado; não conduz a animação.
Rendering é removido ao parar, minimizar ou sair do compacto. O movimento usa
tempo decorrido, portanto limitar FPS não muda a duração.
Referência: [CompositionTarget por frame](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/graphics-multimedia/how-to-render-on-a-per-frame-interval-using-compositiontarget).

SidebarService cuida de janela e hover; CompactDockGeometry calcula
retângulos em pixels físicos, com escalas X/Y separadas. SetWindowPos aplica
posição e tamanho juntos. O frontend recebe tamanho aberto e direção efetiva,
sem substituir a preferência salva Auto. Preserve ColorKey/transparência.

## Áreas e skins

CompactWorkspace possui navegação interna e Voltar. Expandir é uma ação explícita.
IA compartilha conversa selecionada e rascunhos com LocalAiTab. Salas de projeto
mostram um convite para expandir e escolher participantes; o envio simples é
para conversas individuais. Jogos usa a revisão atual no registro rápido.

Aparência oferece seleção da skin e **Editar skin no compacto**. O mesmo
SkinEditorModal da janela completa possui layout estreito, abas Fundo/Cores/
Painéis/Barras/Layout, prévia, desfazer/refazer, descartar, salvar e salvar cópia.
A skin padrão é protegida. Alterar a skin aplica o resultado imediatamente.
O hook useCompactInteraction inclui controles do editor portaled. Chamadas
COM são normalizadas com Promise.resolve antes de catch direto.

StreamProvider também envolve os pontos de entrada independentes watch.html
e StreamViewer; não pressupor que todo visualizador passa pelo App principal.

## Verificação

- Em frontend: npm run build e npm test.
- dotnet run --project scripts/tests/CompactTests/CompactTests.csproj -c Release -- --geometry-only:
  geometria em origens positivas/negativas, escalas 100–200%, borda automática,
  frames intermediários, continuidade, término da animação, cadência e persistência
  de FPS. Executado no CI.
- O mesmo comando sem --geometry-only abre uma janela WPF isolada e verifica
  os monitores conectados, fixação, recolhimento, hover, restauração e persistência.
- node frontend/tests/compact-ui.test.mjs: Edge headless, ponte simulada,
  navegação, altura pequena, skins extremas, editor, chat/rascunho compartilhado,
  interação e ponto de entrada web. Capturas em bin/compact-ui.
- dotnet build -c Release -o bin/CompactDev, seguido de
  powershell -ExecutionPolicy Bypass -File scripts/tests/test_compact_native.ps1:
  aplicativo real + WebView2 + COM com Data/skins isolados. Verifica viewport
  nativo sem emulação, recolhimento nas três direções e quatro opções de FPS,
  canvas estável, prévia,
  cópia salva e expansão. Feche o app antes. Move e restaura o cursor.
  PLAYWRIGHT_MODULE pode apontar para a instalação local do Playwright.
  O log informa mudanças de viewport observadas por requestAnimationFrame e
  maior intervalo entre elas. Isso mede entrega ao renderer, não apresentação
  física do monitor. Não impor um mínimo universal em hardware carregado.

Testes automatizados não medem a percepção de fluidez nem substituem inspeção
física em monitores com escalas distintas. O histórico e próximos incrementos
estão em COMPACT_MODE_NEXT.md.
