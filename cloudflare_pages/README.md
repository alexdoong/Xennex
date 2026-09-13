# Streaming no Cloudflare

O app e o navegador agora usam o mesmo frontend e protocolo `xennex-room-v3`.
A página antiga não é compatível: publique este build antes de enviar convites do app atualizado.

1. Na pasta `frontend`, execute `npm ci` (se necessário) e `npm run build:web`.
2. Publique o conteúdo de `cloudflare_pages/dist/` no seu projeto Cloudflare Pages.
   Não envie a pasta raiz `cloudflare_pages/`, que contém apenas fontes e instruções.
3. Confira no endereço publicado a nova tela de salas e `xennex-stream.json`.
4. Cole a URL HTTPS publicada no campo de endereço público do app.

O arquivo `_headers` gerado libera a leitura do identificador de protocolo pelo app.
O botão de convite no app verifica esse identificador antes de copiar o link.
O build não publica nada automaticamente nem modifica sua conta Cloudflare.

Para integrar um build automatizado, use `frontend` como diretório de trabalho,
`npm run build:web` como comando e a saída `cloudflare_pages/dist` relativa à raiz do repositório.

Cloudflare hospeda a interface. A sinalização usa PeerJS e a mídia usa WebRTC entre
participantes; hospedar a página não fornece um relay de mídia. Redes restritas
podem precisar de TURN. Configure os ambientes conforme `frontend/.env.example`
e recompile tanto o app quanto o site. Não coloque chaves privadas de API nesses
valores: variáveis Vite ficam públicas no JavaScript entregue.

Arquitetura, testes e limitações: [docs/STREAMING.md](../docs/STREAMING.md).
