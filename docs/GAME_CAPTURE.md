# Captura de jogo nativa — protótipo OpenGL (02/11/2026)

Objetivo autorizado: capturar osu! em fullscreen sem depender do aplicativo OBS.
O teste de monitor DXGI/WGC anterior não resolve a apresentação OpenGL exclusiva.
Este é um backend separado, não uma alteração de resolução/FPS nem mudança do jogo.

## Contrato do primeiro protótipo

- DLL própria x86/x64 intercepta SwapBuffers somente no processo e janela escolhidos.
- Leitura OpenGL por PBOs/fences, limitada ao FPS solicitado; não esperar pela GPU
  no callback quando o buffer anterior ainda não estiver pronto. Preservar estado GL.
- IPC por memória/mutex/evento anônimos, com handles duplicados somente para o
  processo alvo; sem endpoint de rede, nomes globais previsíveis ou persistência.
- Worker controla a sessão; encerrar/falhar o worker desativa a captura. Não elevar
  privilégios, mudar anticheat/driver/registro ou capturar outro processo ao perder o alvo.
- Primeiro validar a DLL em um processo OpenGL sintético próprio (sem ler desktop),
  arquitetura, canais, rotação vertical, parada e limites. Só então testar no osu!
  real com autorização explícita para carregar a DLL no processo do jogo.
- Assinar DLL/auxiliar com o publicador existente antes de entregar. Manter fallback
  manual para WGC/DXGI e opção explícita de Captura de jogo; não injetar por padrão.

Build isolado com compilador portátil em bin/, sem instalar toolchain no sistema.
MinHook1.3.4 fornece a interceptação e conserva suas licenças; não incorporar o
código de captura GPL do OBS. Zig0.17.0 fornece compilação C/Win32 x86/x64.

Estado: backend experimental integrado ao app, fonte “Jogo OpenGL · experimental”.
Usuário autorizou o teste real em02/11/2026. No fullscreen apresentado por ele,
osu!32 produziu30,0/60,0/119,7FPS nos alvos30/60/120, com conteúdo mudando e parada
correta; sem OBS. Isso substitui o gargalo DXGI anterior de1–2FPS neste ensaio.
Apenas OpenGL desktop; não implementa captura direta DirectX/Vulkan.

Uso: Transmissões → Compartilhar tela → Jogo OpenGL → janela do jogo, qualidade
e áudio → iniciar → voltar ao jogo. Se outra versão/cópia da DLL já estiver
carregada, reiniciar o jogo antes da captura atualizada. O auxiliar recusa sobrepor
módulos de caminhos diferentes. Não altera configurações, captura outro processo
ou monitor, usa OBS ou eleva privilégios.

## Build e testes

```powershell
# Prepara compilador em bin/, com SHA-256 fixado; não instala no Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_game_capture.ps1 -PrepareTools
# Assina com a identidade existente; não cria certificados.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_game_capture.ps1 -SignPrototype
dotnet run --project scripts/tests/CaptureWorkerTests -c Release -- --game-hook --native-directory "E:\Projetos e apps\Xennex\bin\GameCaptureNative"
dotnet run --project scripts/tests/CaptureWorkerTests -c Release -- --verify-game-hook --native-directory "E:\Projetos e apps\Xennex\bin\GameCaptureNative"
```

`--game-hook` cria dois processos OpenGL próprios ocultos; não lê desktop nem toma
foco. Confere BGRA/origem inferior, conteúdo móvel, timestamps, preservação do
estado GL, redimensionamento e três ciclos de parada/reinício nos alvos30/60/120.
IDs de quadros produzidos medem a cadência; amostras do consumidor podem perder
IDs por projeto, pois o IPC retém apenas a imagem mais recente. Não mede JPEG,
WebRTC ou FPS recebidos por amigos. Logs: bin/game-hook-test.log.

MinHook1.3.4 foi versionado em Native/ThirdParty/MinHook com fontes/licenças
originais (BSD2 e avisos HDE). Nenhum código/binário de captura do OBS foi copiado.
Zig0.17.0 oficial, ZIP SHA-256
`b5663f69581dcf391293fbf16c06cb80d81d806545ce618b4d0bab7f0eb8c428`.
Notices de runtime Zig/MinGW ficam em assets/licenses e acompanham o pacote.

## Ciclo de vida e limites

- Até três PBOs e uma superfície IPC de32MiB. Drena somente buffers prontos na
  cadência de render, separada do FPS de captura; publica o mais recente, sem
  esperar três períodos só para girar a fila. Fence/mutex sem espera intencional;
  driver GL e cópia de pixels ainda custam tempo. Não é zero-copy/encoder hardware.
- Renderização concorrente usa tentativa sem bloqueio; reentrância entre pontos
  SwapBuffers é suprimida. Estado gráfico alterado é restaurado.
- Parada desativa hooks e fecha IPC; tenta liberar PBOs no contexto GL correto.
  Se o jogo não renderizar, objetos GL podem permanecer até o contexto acabar.
  DLL e trampolines ficam residentes e desativados até o processo encerrar, evitando
  remover instruções às quais outra thread ainda poderia retornar. Próxima sessão
  reutiliza o módulo e descarta buffers anteriores antes de publicar imagens.
- Mudança inesperada de contexto falha explicitamente; nunca deleta objetos no
  contexto errado. wglDeleteContext invalida a sessão mesmo se o handle GL for
  reutilizado; após destruir contexto ou falhar limpeza, exige reinício do jogo.
  Prazo de limpeza usa relógio real, sem depender da precisão de Sleep. Teste
  sintético recria o contexto, verifica jogo vivo, captura encerrada e recusa
  de reuso. Recuperação automática de contexto/driver continua fora do escopo.
- Auxiliar aceita somente sua DLL correspondente ao lado do próprio executável,
  processo da mesma conta e arquitetura compatível. Probe real exige integridade
  Authenticode e publicador fixado. Sem elevação/bypass de anticheat/registro/driver.
- Falha de inicialização concluída devolve handles duplicados. Timeout de thread
  remota não termina a thread nem libera argumentos/handles que ela pode usar.
  Esse estado ambíguo precisa limitar novas tentativas na integração de produção.

## Probe real autorizado

```powershell
dotnet run --project scripts/tests/CaptureWorkerTests -c Release -- --osu-game-hook --authorize-game-hook --native-directory "E:\Projetos e apps\Xennex\bin\GameCaptureNative"
```

Espera até90s pelo jogo em primeiro plano; mede três etapas curtas30/60/120,
sem imagens salvas, alterações de configuração, OBS ou encerramento do jogo.
Alt+Tab interrompe; só o processo/janela escolhidos são elegíveis. Reiniciar o
jogo remove o módulo residente. Hook pode causar falha do jogo. Registra apenas
contagens/tempos/fingerprints agregados: bin/osu-game-hook.log.

## Integração e verificação de ponta a ponta

NativeGameSession valida PID/HWND/início do processo, arquitetura, assinatura e
publicador dos dois binários usados; cria IPC anônimo e inicia o auxiliar uma vez.
Sem retry automático de injeção nem fallback para outro processo ou monitor.
GameFrameEncoder interpreta BGRA inferior com stride negativo; mantém proporção,
não amplia e codifica JPEG. Worker consulta o último quadro com timer privado de
alta resolução, sem alterar a resolução global de timers do Windows. Ausência
de quadros por20s encerra, sem congelamento silencioso indefinido.

Ponte BeginGameCapture usa o mesmo dono/cancelamento do vídeo e áudio nativos.
Áudio pode vir do jogo ou de outro processo selecionado. Fontes browser/WGC/DXGI
continuam independentes; o modo de jogo exige seleção explícita. Binários runtime
vão em GameCapture/; o empacotador compila/assina os quatro e inclui a licença
MinHook. Fixture e compilador não entram no pacote. Worker verifica as assinaturas
antes de tocar o jogo; atualizador também verifica o grupo se ele estiver presente.

Testes determinísticos de CI: limites/overflow de frames, orientação e redução
de JPEG, posse da sessão, seleção PID/HWND/qualidade e ausência de fallback.
Teste opt-in IPC→JPEG→socket autentica com token/origem, cria só processos GL
próprios x86/x64, mede30/60/120 e encerra abruptamente Workers repetidos; também
recusa segunda cópia de DLL em outro caminho. Imagens não são salvas.

```powershell
dotnet run --project scripts/tests/CaptureWorkerTests -c Release -- --game-worker --native-directory "E:\Projetos e apps\Xennex\bin\GameCaptureIntegrated" --worker "E:\Projetos e apps\Xennex\src\CaptureWorker\bin\Release\net8.0-windows10.0.19041.0\Xennex.CaptureWorker.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_stream_native.ps1 -GameCapture
```

O último comando requer app principal fechado, pacote oficial existente e
bin/GameCaptureIntegrated/Xennex.OpenGlFixture64.exe preparado pelo build com
`-OutputDirectory bin/GameCaptureIntegrated -SignPrototype`. O teste cria cópia
isolada sem Data/ e captura somente a fixture; sem foco, monitor ou jogo pessoal.

No ensaio sintético completo com qualidade preservada, receiver WebRTC local
recebeu aproximadamente29,9/57,4/83,1FPS nos alvos30/60/120, em644×480, mantendo
dimensões do Worker. Captura bruta/Worker próximos de120 não garantem120 no amigo:
JPEG/decode/canvas/encoder/rede ainda limitam. Logs: bin/game-worker-test.log e
bin/game-capture-webview.log. Não comprova1080p120/1440p120 nem redes distintas.
