# Streaming — desenvolvimento 0.2.x

A versão do projeto permanece 0.2.2. Esta revisão não é uma release distribuível
nem uma publicação no Cloudflare. O estado anterior desta etapa foi salvo em
`Backup/streaming-before-20260912-003323.zip`.

## Arquitetura

`frontend/src/features/stream/StreamWorkspace.tsx` é a interface compartilhada
pelo app, janela separada e navegador. `RoomClient.ts` mantém presença, mensagens,
assinaturas de vídeo, reconexão e encerramento. `protocol.ts` valida mensagens;
`quality.ts` calcula proporção e orçamento de upload; `capture.ts` gerencia mídia
e limpeza; `StreamVideo.tsx` apresenta vídeo e controles; `RoomDiagnostics.tsx`
mostra estatísticas reais de conexão. A aba permanece montada durante a navegação.

Cada participante usa uma identidade de mídia estável. `RoomCoordinator.ts` recebe
presença e autoriza assinaturas por uma segunda identidade PeerJS, ligada ao código
da sala. O coordenador não retransmite vídeos. Quando ele sai ou cai, os demais
competem pelo mesmo identificador de coordenação com atrasos ordenados; PeerServer
concede esse identificador a apenas um deles. O vencedor reconstrói a presença e
assinaturas. As conexões de mídia existentes entre sobreviventes permanecem abertas.
A eleição pode levar alguns segundos e depende da disponibilidade da sinalização.
Não existe mais botão de encerrar a sala para todos: cada pessoa sai individualmente.
A saída da última pessoa libera o código. Não há sala persistente vazia no servidor.

Limites de desenvolvimento: 32 participantes, seis fontes simultâneas por pessoa,
e até 32 fontes assistidas por participante. Toda pessoa pode transmitir enquanto
assiste. O catálogo identifica cada tela/câmera separadamente. Não há assinatura
automática: cada espectador escolhe fontes e ativa áudio/volume independentemente.
Destacar um vídeo mantém os outros áudios selecionados em reprodução.

App e navegador permitem várias telas e câmera (inclusive duas telas mais câmera).
Cada nova tela abre o seletor do navegador; câmera pode incluir microfone. No app,
existe também captura nativa com áudio de processo. Esse pipeline nativo permanece
limitado a uma fonte por instância: use o seletor para as telas adicionais. As opções
de áudio das telas do navegador dependem da fonte e das permissões do browser.

A resolução é selecionável de 720p a 4K ou Original, por fonte. FPS aceita valores
inteiros de 0 a 120: 0 é automático, 1 a 120 são limites solicitados. No pipeline
nativo e na codificação o modo automático usa teto de 120; no seletor não fixa uma
taxa de captura. Um pedido de 120 FPS não garante 120 quadros reais. Fonte, câmera,
GPU, CPU e conexão podem entregar menos. O capturador nativo respeita também 1–14 FPS.

Os códigos são convites, não autenticação de usuários. O limite de participantes
não é garantia de desempenho: a mídia ainda é P2P, com uma cópia por espectador e
fonte. O orçamento informado é compartilhado entre todas as conexões de envio.
Para um grupo grande assistindo a muitas fontes em alta qualidade, a evolução de
infraestrutura é um SFU; ampliar o limite da sala não elimina esse custo de upload.

A captura nativa passa por Windows Graphics Capture, leitura de textura, JPEG,
WebSocket local, canvas e WebRTC. Preserva proporção, evita ampliar fontes menores
e ajusta textura ao redimensionar a janela. Ainda há custo de CPU/cópias: não é
um encoder de hardware com caminho sem cópias. A taxa de amostragem do áudio vem
do serviço nativo; o WebAudio faz a conversão, sem ganho artificial.
`CaptureSessionService` impede duas janelas de controlar a mesma captura.

A resolução/FPS escolhida é um limite solicitado, não garantia. WebRTC adapta
à rede e ao hardware. O orçamento de upload é dividido entre espectadores com
margem; aumentar espectadores exige mais upload. O tile mostra resolução recebida,
e o diagnóstico informa bitrate, latência e uso de relay quando disponíveis.

## Testar localmente

Na raiz, execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_dev.ps1 -StreamingPreview
```

Isso compila e abre `bin/StreamingPreview/net8.0-windows/Xennex.exe`, usando dados
locais dessa saída. Feche sua instância anterior antes de abrir a nova, pois há
controle de instância única. Para somente compilar, acrescente `-BuildOnly`.
Este build requer o ambiente de desenvolvimento; para distribuir aos amigos,
use exclusivamente o empacotador obrigatório descrito em AGENTS.md.

Para o browser, em `frontend`, execute `npm run build:web`. Sirva
`cloudflare_pages/dist` por HTTP em localhost (ex.: Python http.server), ou HTTPS
no Cloudflare. Compartilhamento de tela requer contexto seguro e clique do usuário.

## Validação automatizada e manual

- `npm test` em `frontend`: contratos, proporção, bitrate, presença, identidade,
  múltiplas fontes, escolha independente, saída, migração normal/abrupta, entrada
  após migração, 12 participantes simulados, admissão de 32 e rejeição do 33º.
- `npm run build` e `npm run build:web`: TypeScript estrito e bundles separados.
- `frontend/tests/browser-streaming.mjs`: Edge headless com Playwright; exige
  módulo Playwright disponível por `XENNEX_PLAYWRIGHT_PATH` e site servido em
  `http://127.0.0.1:5179` (ou `XENNEX_TEST_URL`). Usa sinalização PeerJS real,
  sessões WebRTC com três transmissores, duas telas mais câmera, áudio simultâneo,
  saída/migração, entrada tardia e fechamento abrupto do coordenador. Usa fontes
  sintéticas e não captura tela, microfone ou câmera pessoais.
- `scripts/tests/test_release.ps1`: validações isoladas de empacotamento/atualização.

Antes de considerar estável, testar manualmente: app ↔ navegador em PCs/redes
diferentes; áudio de processo e sistema; janela redimensionada/minimizada; monitor
ultrawide; troca de abas; fechar popout; cancelar seletor; suspensão/reconexão;
mais espectadores e redes que exigem TURN. Os testes sintéticos não validam esses
casos nem comprovam qualidade de áudio capturado no Windows.

## Publicação web e compatibilidade

O protocolo novo é `xennex-room-v3`, incompatível com a página antiga. Atualize
app e site juntos. Veja [Cloudflare](../cloudflare_pages/README.md). Nenhum deploy
é feito pelo build. O app verifica `xennex-stream.json` antes de copiar convite.
A sinalização padrão depende do serviço público PeerJS; TURN não vem configurado.
A configuração opcional fica em `frontend/.env.example` e deve ser igual nos dois
builds. Credenciais incluídas no frontend são públicas; não use segredos de conta.


Referências de API: [ciclo de vida PeerJS](https://peerjs.com/client/api/peer) e
[restrições de FPS](https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/frameRate).

## Entrada em salas de versões anteriores

Salas abertas pelo app/site antigo não aparecem no protocolo atual, mesmo que o
código seja igual. Antes de atualizar o Cloudflare, teste somente entre instâncias
do app atualizado ou a página local gerada. A primeira pessoa usa Criar sala;
as demais usam Entrar. A página pública precisa de um novo deploy do dist.
O diagnóstico agora distingue sala não encontrada, falha na sinalização e timeout
de conexão. Uma negociação pendente tem 15 segundos antes de ser refeita, evitando
o reinício prematuro a cada cinco segundos; há teste de uma conexão de 6,5 segundos.

### Verificação no app completo (12/09/2026)

Criação e retorno à sala passaram em três ciclos no WebView2 real, com um
participante no Edge e migração entre eles. O teste reproduzível está em
`frontend/tests/webview-room-entry.cjs`: use uma instância de teste do app com
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9226`, site local
na porta 5179 e Playwright em `XENNEX_PLAYWRIGHT_PATH`. Ele encerra essa instância
após os testes; não execute durante uma sessão pessoal. A porta de diagnóstico
não é habilitada nos builds normais.

Também foram validadas conexão de 6,5 segundos e recuperação após falha temporária
no registro do coordenador. Opções da conexão → Diagnóstico da conexão mostra as
últimas etapas em caso de falha. A falha relatada não foi reproduzida no app antigo
nesta rodada, portanto não se atribui com certeza a ocorrência a uma causa única.
