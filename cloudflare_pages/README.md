# Streaming no Cloudflare

## Entrega de 03/11/2026

Versão publicada `19acaf94-1078-4aaa-bb7d-759b1e847e95`: diagnóstico estruturado
da entrada, layouts locais/foco com miniaturas/encaixe, medição voluntária RTP e
taxas de chegada separadas de decode com estado de foco. Bundle público conferido
por hash contra dist (`assets/index-laLhQhd1.js`). Protocolo xennex-room-v3;
broker continua503/turn_disabled. Nenhum serviço ou cobrança novo ativado.
Rollback imediato: `e12e0ef9-509f-43d3-9b2f-09475c2876ea`; versão anterior ao
lote: `ad351977-0b4d-4646-bfc2-cc3c1465e61d`. Registros abaixo são históricos.

## Compatibilidade no navegador

O site é a experiência principal do grupo; não exige o app Windows. Em Transmitir
→ Ajustes avançados, o formato pode ser Automático, compatibilidade ou preferência
de codec. Quem assiste tem opção própria em Qualidade → Compatibilidade deste
dispositivo. A negociação preserva alternativas por conexão; AV1 não é obrigatório.
Sem captura de tela no navegador/dispositivo, ainda é possível assistir quando
WebRTC é suportado. Detecção de eficiência é estimativa, não garantia de hardware.
Ver [contrato e testes](../docs/STREAMING_CAPABILITIES.md).

O app e o navegador agora usam o mesmo frontend e protocolo `xennex-room-v3`.
A página antiga não é compatível: publique este build antes de enviar convites do app atualizado.

O projeto atual é um **Worker com Static Assets**, publicado pelo Wrangler.
O uploader de arquivos estáticos do painel não publica `worker.mjs` e não aceita
a pasta de fontes com `wrangler.jsonc`. Não enviar `cloudflare_pages/` inteira
nem colocar `dist/` dentro de outra pasta no site.

Na raiz do repositório, usando Wrangler 4.156.1:

```powershell
# Uma vez nesta máquina; a autorização é feita pelo dono da conta no navegador.
npx --yes wrangler@4.156.1 login --scopes account:read user:read workers_scripts:write
# Se o navegador não abrir ou o callback local falhar:
# npx --yes wrangler@4.156.1 login --device --browser=false --scopes account:read user:read workers_scripts:write
npx --yes wrangler@4.156.1 whoami

Push-Location frontend
npm run build:web
Pop-Location
npx --yes wrangler@4.156.1 deploy --config cloudflare_pages/wrangler.jsonc --dry-run
npx --yes wrangler@4.156.1 deploy --config cloudflare_pages/wrangler.jsonc
```

Antes de publicar, conferir a conta/nome do Worker e o histórico remoto para
permitir rollback. O deploy envia apenas o Worker e os assets compilados de
`dist/`, sem `Data/`, credenciais locais ou modelos. Não executar `--temporary`,
pois isso cria outra hospedagem em vez de atualizar a existente.

Depois, conferir a tela de salas, JS/CSS e `xennex-stream.json` no endereço
publicado. O protocolo deve ser `xennex-room-v3`; manter essa URL HTTPS no campo
de endereço público do app. O POST `/api/turn-credentials` deve responder
`503 {"error":"turn_disabled"}` enquanto o TURN estiver desligado.

Para hospedagem **apenas estática** em outro projeto Pages, o upload manual seria
somente do **conteúdo** de `dist/`. Essa alternativa não instala o broker.

O arquivo `_headers` gerado libera a leitura do identificador de protocolo pelo app.
O botão de convite no app verifica esse identificador antes de copiar o link.
O build não publica nada automaticamente. Somente o comando `deploy` atualiza a conta.

Para integrar um build automatizado, use `frontend` como diretório de trabalho,
`npm run build:web` como comando e a saída `cloudflare_pages/dist` relativa à raiz do repositório.

Cloudflare hospeda a interface. A sinalização usa PeerJS e a mídia usa WebRTC entre
participantes; hospedar a página não fornece um relay de mídia. Redes restritas
podem precisar de TURN. Configure os ambientes conforme `frontend/.env.example`
e recompile tanto o app quanto o site. Não coloque chaves privadas de API nesses
valores: variáveis Vite ficam públicas no JavaScript entregue.

Arquitetura, testes e limitações: [docs/STREAMING.md](../docs/STREAMING.md).

## TURN opcional no Workers

`worker.mjs` e `wrangler.jsonc` acrescentam um broker de credenciais à mesma
hospedagem. TURN fica **desligado por padrão**; o site e o P2P continuam disponíveis.
Somente um participante que escolher a alternativa solicita acesso, com código
privado. Publicar apenas dist não publica o broker. Não foram criados secrets nem
feita ativação de TURN com esses comandos. Configuração, testes, reversão e restrição de custo
zero: [STREAMING_TURN.md](../docs/STREAMING_TURN.md).


## Publicação verificada em 01/11/2026

Produção: https://xennex-live.alexdoong11.workers.dev
Versão: `b7dad075-8858-4d5a-9b95-49eb00353e4a`.
Worker+assets verificados por HTTP e salas com três publicadores no navegador.
TURN desligado; publicar o broker não ativa o relay.


Atualização de transmissão (01–02/11/2026): versão
`8cab7830-3547-48fa-9ba9-6567ffea65eb`, com métricas novas de codec/decode/buffer,
fila recente e avisos de instabilidade. Testes em sala separada no endereço real
passaram; TURN permanece desligado. A versão entra ao recarregar a página.
