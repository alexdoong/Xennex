# Gestures

Gestures transforma landmarks da mão em eventos de reconhecimento e ações do Windows. A câmera começa sempre em **modo de teste**. Não é necessário criar uma sala de streaming para utilizá-lo.

## Uso no aplicativo

1. Abra **Gestures** e clique em **Iniciar câmera em teste**. O índice 0 representa a primeira câmera.
2. Confira os pontos da mão e o último gesto reconhecido. Use boa iluminação e mantenha a mão inteira visível.
3. Ajuste as associações e salve. As ações continuam pausadas após salvar.
4. Clique em **Ativar controle do PC** para permitir comandos. **Esc** pausa imediatamente; perder a mão solta o arraste. A câmera pode continuar ligada durante a pausa.

Padrões disponíveis:

| Gesto | Ação inicial |
| --- | --- |
| Indicador estendido, demais dedos recolhidos | Mover o cursor |
| Pinch entre polegar e indicador | Segurar e mover uma janela |
| Palma aberta movendo para esquerda/direita/cima/baixo | Win+Left/Right/Up/Down |

A imagem é espelhada: direita corresponde à direita na prévia. O cursor usa os 80% centrais da imagem e o desktop virtual, incluindo monitores adicionais. A suavização reduz pequenas oscilações.

No modo **barra de título**, posicione o indicador sobre uma barra de título reconhecida pelo Windows antes do pinch. Solte os dedos para largar a janela. O modo **janela ativa** move a janela que já está em primeiro plano. A janela precisa estar restaurada: o motor não arrasta janelas minimizadas/maximizadas. Barras personalizadas podem precisar do modo janela ativa.

As ações podem ser trocadas por clique esquerdo/direito/duplo, arraste com botão esquerdo, rolagem vertical, movimento do cursor, movimento de janela ou atalho. Atalhos aceitam até cinco teclas, como `ctrl+alt+m`, `win+left`, `alt+tab` e `playpause`. Combinações reservadas pelo Windows podem ser interceptadas pelo próprio sistema; o campo de texto permite configurá-las sem pressioná-las.

## Gravação de gestos próprios

Crie uma **pose parada** ou um **movimento**, escolha a ação e grave exemplos. A gravação tem três segundos de preparação, seguidos de um segundo para poses ou dois segundos para movimentos. O app salva automaticamente ao terminar; é possível cancelar.

Comece com três exemplos semelhantes. Cada gesto aceita até oito amostras; o perfil aceita até 40 gestos. O movimento precisa deslocar a mão, e não somente mexer os dedos mantendo o punho imóvel. Se perder a mão, trocar a mão ou receber poucos quadros durante a captura, a amostra é rejeitada.

As amostras guardam coordenadas dos 21 pontos, duração e mão utilizada. Fotos e vídeos não são gravados. A identificação é por comparação geométrica e temporal, sem treinar uma rede neural pessoal.

A tolerância menor exige uma correspondência mais próxima. Poses aprendidas têm prioridade sobre os padrões quando correspondem; amostras aprendidas muito parecidas entre si podem ser consideradas ambíguas e não disparar nada. Desabilite associações concorrentes e teste antes de controlar o PC.

## Memória e compatibilidade

`Data/gesture_profiles.json` contém associações e amostras. O serviço C# é o único escritor; salva por substituição atômica e mantém a versão anterior em `.bak`. Alterações da interface preservam amostras gravadas mais recentemente.

Na primeira abertura, o serviço tenta importar `Data/gestures.json` e `Data/swipe_config.json`. Os originais permanecem intactos. Poses antigas entram desabilitadas para revisão; itens inválidos geram um aviso no perfil. Um perfil atual corrompido gera erro, em vez de ser substituído silenciosamente.

A pasta pessoal `Data/`, o ambiente Python, caches e executáveis permanecem ignorados pelo Git. O pacote usa somente os modelos públicos de `assets/defaults/`.

## Arquitetura

- `frontend/src/features/hand-motion/`: tela, editor de associações, pontos da mão e sincronização com o backend. O identificador antigo da aba é mantido por compatibilidade.
- `src/Interop/ApiBridge.cs`: encaminha chamadas tipadas no `webview.d.ts`.
- `src/Services/HandMotionService.cs`: supervisiona o processo e troca comandos/eventos JSON. Gravações recebem um token para descartar respostas canceladas.
- `src/Services/Gestures/`: validação, memória e migração.
- `scripts/gestures/tracking.py`: câmera e landmarks MediaPipe.
- `features.py`, `recognition.py` e `recording.py`: geometria normalizada, DTW de sequências e captura de exemplos.
- `control.py`: autorização temporária para emitir comandos; um watchdog pausa após 800 ms sem progresso ou ao pressionar Esc.
- `windows_actions.py`: adaptador Win32 para cursor, teclado e janelas, sem PyAutoGUI.
- `runtime.py`: coordena os módulos. `hand_motion.py` permanece como ponto de entrada.

As ações contínuas emitem begin/update/end. Atalhos e cliques exigem liberação da pose antes de repetir; swipes também compartilham um intervalo para não interpretar imediatamente o retorno da mão como outro comando.

## Desenvolvimento e distribuição

Para executar o código Python em desenvolvimento, use Python 3.11 x64 e:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_gestures.ps1
```

Isso cria `.venv/` e instala versões compatíveis de MediaPipe, OpenCV e NumPy. O teste de dependências carrega o modelo e processa uma imagem sintética, sem abrir a câmera.

O motor autocontido é compilado por `scripts/build_gestures.ps1`. O PyInstaller inclui Python, dependências e modelos dentro de `Xennex.GesturesWorker.exe`. Nas releases, ele acompanha o aplicativo na pasta `scripts/`; usuários finais não precisam instalar Python. O serviço prefere esse executável. Em desenvolvimento, `XENNEX_GESTURE_PYTHON` permite indicar explicitamente outro ambiente isolado.

Releases continuam sendo geradas somente por `scripts/package_release.ps1`, que compila, valida e assina os executáveis. A versão continua vindo de `Xennex.csproj`.

## Verificações

```powershell
.venv/Scripts/python.exe -m unittest discover -s scripts/tests -p test_gestures.py -v
dotnet run --project scripts/tests/GestureTests/GestureTests.csproj -- .venv/Scripts/python.exe
powershell -ExecutionPolicy Bypass -File scripts/tests/test_release.ps1
```

O teste visual `frontend/tests/gestures-ui.test.mjs` usa Playwright com Edge headless e a API simulada, após `npm run build`. A variável `PLAYWRIGHT_MODULE` pode apontar para uma instalação existente do Playwright.

Testes automatizados não abrem a câmera nem pressionam teclas reais. Eles cobrem landmarks sintéticos, eventos, memória, migração, comunicação, modos de controle e interface. A validação com câmera física, iluminação real e aplicações de terceiros continua necessária.

## Limites e próximos passos

Esta implementação reconhece uma mão por vez. O esquema e a separação de rastreador/reconhecedor/ações permitem acrescentar provedores de corpo e áudio, mas poses corporais e palmas ainda não estão implementadas. Mudar muito a orientação da mão ou a perspectiva exige novos exemplos. O sistema não garante controle de qualquer aplicativo nem substitui todos os métodos de entrada do Windows.

O Windows pode impedir entrada em janelas com privilégios superiores e telas protegidas. Falhas de entrada pausam os comandos e são mostradas na interface.

Referências: [MediaPipe Hands](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/hands.md), [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput), [WM_NCHITTEST](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest), [PyInstaller](https://pyinstaller.org/en/stable/usage.html).

## Fluidez e diagnóstico

A captura usa uma fila de um quadro: a análise recebe o mais recente, sem acumular atraso quando demora mais que a câmera. O rastreador procura uma mão por vez; mantenha somente a mão escolhida no enquadramento. Desenhos sobre o vídeo só são calculados com a prévia de vídeo aberta.

A visualização dos pontos recebe atualizações até aproximadamente 25 vezes por segundo, limitada pela captura real. O painel mostra FPS processado, tempo da visão e idade do quadro. A taxa solicitada à câmera é 30 FPS; câmera, driver e iluminação podem entregar menos.

A suavização do cursor considera o tempo entre quadros e reduz o atraso em movimentos amplos, mesmo com o ajuste alto. Um pinch sem barra de título ou sobre janela maximizada cancela somente essa tentativa; solte o pinch antes de tentar novamente. Esc, falha real de entrada e interrupção prolongada continuam pausando o controle, com o motivo na tela.

Para medir explicitamente a câmera sem ações no desktop e sem gravar imagens:
powershell: .venv/Scripts/python.exe scripts/tests/benchmark_gestures.py --camera 0 --seconds 70

Regressões adicionais: scripts/tests/test_gestures_performance.py.
