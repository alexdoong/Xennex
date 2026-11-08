# Transmissão de tela no Android

## Estado em 08/11/2026

Prévia nativa em `src/Android`, separada do app Windows. Compilada para Android
8/API 26 ou superior. A captura usa MediaProjection + libwebrtc; não depende
de `getDisplayMedia`, WebView, canvas/JPEG ou de manter o navegador em foco.
**Compilação/testes locais não substituem o ensaio num aparelho real, ainda pendente.**

O caminho completo implementado é: autorização do Android → serviço de captura
em primeiro plano → textura/encoder WebRTC → assinatura de publicação da sala
v3 → espectador no site existente. Cloudflare continua hospedando o site;
PeerServer negocia conexões e STUN auxilia o P2P. TURN permanece desligado.
Redes que impedem P2P ainda podem falhar; o APK não elimina essa limitação.

## Como testar com o grupo

1. Alguém abre/cria a sala no site ou no Xennex Windows e permanece nela.
2. No Android, instalar manualmente o APK de prévia fornecido pelo desenvolvedor.
   Não é necessário instalar Android Studio, Java, certificado Windows ou OBS.
3. Abrir **Xennex Live**, preencher código/link da sala e nome, tocar em
   **Entrar e compartilhar tela** e confirmar a seleção do Android.
4. Os amigos escolhem **Assistir** na publicação **Tela do Android** da sala.
5. Encerrar pelo botão do app ou pela ação **Parar** da notificação do sistema.

O link opcional `xennex-live://share?room=CODIGO` apenas preenche a sala. Nunca
inicia captura automaticamente. O botão correspondente foi adicionado ao código
web para dispositivos sem API de tela; depende do APK instalado e de publicar
esse novo build do site. Também é possível digitar o código, sem atualização web.

Esta prévia compartilha **somente vídeo**, sem microfone ou áudio interno.
Alvo: 30 FPS, maior dimensão de até 1280 pixels, aspecto preservado, sem upscale.
Até quatro conexões de espectadores e orçamento agregado solicitado de 8 Mbps,
dividido entre elas. Negociação, encoder, aparelho e rede determinam o resultado
real. Esses valores não representam desempenho medido no telefone.

Não cria nem assume coordenação de salas; um participante web/Windows deve
permanecer. Tenta reencontrar o coordenador durante migração, com envio pausado
até receber presença válida. Falhas de sinalização encerram a captura com aviso;
é necessário entrar novamente. Não recebe vídeo/chat dos outros dentro do APK.
Não inclui iOS, áudio interno, controles avançados ou distribuição automática.

## Responsabilidades e limites

- `MainActivity`: formulário, link de entrada e consentimento explícito.
- `CaptureService`: notificação persistente, ciclo da sessão, `START_NOT_STICKY`;
  não reinicia captura após encerramento/morte do processo.
- `AndroidCapture` / `CaptureSize`: projeção, textura, dimensões pares, rotação,
  liberação de recursos; usa callback de tamanho do conteúdo a partir do Android14.
- `AndroidRoomClient`: presença/publicação/assinaturas/heartbeat e recuperação.
- `RoomRoster`: contrato de presença validado antes de autorizar espectadores.
- `PeerSignaling`: socket WSS PeerServer, sem mídia e sem logs de SDP/candidatos.
- `PeerLink`: oferta/resposta/ICE/canal JSON binário compatível com PeerJS1.5.5,
  bitrate por receptor, prazos e descarte das conexões.

IDs de sessão/publicação aleatórios, não persistidos. Link colado fornece somente
código da sala; não muda servidor nem carrega configurações remotas. Serviço não
exportado. Não solicita câmera, microfone ou armazenamento. Não salva imagens.
Sem TURN, captura oculta, reinício no boot ou execução de comandos recebidos.
Confia na coordenação da sala da mesma forma que os clientes atuais: código de
sala/presença não equivale a autenticação forte de identidade.

Mensagens/candidatos, participantes, publicações, filas e espectadores são
limitados. Uma presença inválida não autoriza envio. Perder a coordenação fecha
as conexões de mídia; parar encerra conexões antes de liberar factory/textura.
Conteúdo protegido por outros apps pode aparecer preto: não há contorno de DRM
ou de `FLAG_SECURE`.

## Compilar e verificar

JDK17, Gradle8.11.1, Android SDK35/build-tools35.0.0; plugin Android8.9.2.
Dependências fixadas: `io.github.webrtc-sdk:android:150.7871.01`, OkHttp4.12.0.
JUnit4.13.2 e org.json20240303 somente nos testes.

Ferramentas locais ficam em `bin/AndroidTools` (ignorado no Git):
`java/<jdk>/`, `gradle-8.11.1/`, `sdk/` e `gradle-home/`.
O setup desta máquina baixou arquivos oficiais e verificou os checksums antes
da extração. Não alterou PATH global ou a instalação do Xennex Windows.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_android.ps1
```

Executa `assembleDebug`, `testDebugUnitTest` e `lintDebug`. APK em
`src/Android/app/build/outputs/apk/debug/app-debug.apk`. É assinado com chave
**de desenvolvimento**, não uma release de produção. Preservar a chave de
assinatura antes de estabelecer distribuição/atualizações duradouras.
O aplicativo não instala atualizações nem se instala em aparelhos automaticamente.

O projeto também abre no Android Studio; configurar SDK35 e JDK17 e usar Gradle
8.11.1. SDK/cache/APK/keystores não devem entrar no Git nem no pacote Windows.
Avisos de terceiros estão empacotados em `app/src/main/assets/licenses/`.

Verificações locais: normalização/rejeição de códigos e links, dimensões/aspecto,
presença válida, identidade/publicação própria, duplicatas, tipos e limites.
Suite web cobre APIs ausentes, contexto inseguro, política e erros sem inferir
causa; o teste de navegador cobre recepção com capacidades limitadas e o link
Android. Essas verificações **não testam libwebrtc/MediaProjection num Android**.

Ensaio de aceitação pendente: aparelho/versão; autorização/cancelamento; imagem
em movimento chegando ao navegador; retrato/paisagem; app em segundo plano;
parar pelo sistema/notificação; sair/reentrar; 1–4 espectadores; troca Wi-Fi/dados;
uma rede sem P2P; conteúdo protegido; repetidas sessões sem recursos presos.

## Referências técnicas

- [Android MediaProjection](https://developer.android.com/media/grow/media-projection)
- [Compatibilidade do Android Gradle Plugin8.9](https://developer.android.com/build/releases/agp-8-9-0-release-notes)
- [Distribuição WebRTC Android](https://github.com/webrtc-sdk/android)
- Protocolo do cliente PeerJS instalado: `frontend/node_modules/peerjs/dist/peerjs.js`.

Áudio interno requer AudioPlaybackCapture (Android10+) e a autorização de captura
dos aplicativos de origem. Deve ser uma opção explícita com ciclo de vida próprio,
sem misturar o microfone automaticamente. Implementar após validar este caminho de vídeo.
