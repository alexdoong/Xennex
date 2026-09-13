# Interface do Xennex

React + TypeScript em modo estrito, compilado pelo Vite para `../wwwroot/`.

```powershell
npm ci
npm run dev
npm run build
npm run build:web
npm test
npm run lint
```

O navegador de desenvolvimento não fornece a ponte nativa do WebView2. Para
validar os recursos Windows, use `../scripts/run_dev.ps1` a partir do projeto.

- `src/features/`: funcionalidades e suas abas.
- `src/layout/`: navegação e moldura do aplicativo.
- `src/hooks/`: estado compartilhado e comportamentos reutilizáveis.
- `src/components/`: componentes comuns.
- `src/styles/`: módulos CSS, na ordem de `src/index.css`.
- `src/webview.d.ts`: contrato nativo e modelos compartilhados.
- `watch.html`: visualizador web independente.

O build preserva o conteúdo de `wwwroot/` para não apagar skins locais.
O empacotador aplica a filtragem para a distribuição.

Consulte [as regras de codagem](../docs/CODING_RULES.md),
[o contexto](../docs/AGENT_CONTEXT.md) e [o roteiro de testes](../docs/TESTING.md).

O app e a página web compartilham `src/features/stream/`. O build web sai em
`cloudflare_pages/dist/`. Veja [STREAMING.md](../docs/STREAMING.md).
