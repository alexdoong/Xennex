# Xennex — arquitetura e contexto

## Fluxo principal

O Xennex combina .NET 8/WPF e WebView2 com React/TypeScript. A janela hospeda
`https://appassets/index.html`, mapeado para a pasta externa `wwwroot/`.
O frontend chama `window.chrome.webview.hostObjects.api`; `ApiBridge` delega
para os serviços C#. A janela também recebe mensagens de arraste e resize.

A transparência usa Win32 e ColorKey. Preserve o mecanismo da janela ao mexer
na interface; alterações visuais devem ocorrer no React/CSS.

## Mapa do código

| Diretório/arquivo | Responsabilidade |
| --- | --- |
| `src/Program.cs` | Entrada, instância única e registro de exceções globais |
| `src/UI/` | Janelas WPF, WebView2, bandeja e ciclo de vida visual |
| `src/Interop/ApiBridge.cs` | Contrato COM de comunicação com os serviços |
| `src/Models/` | Configuração, skins, builds e resultado de atualização |
| `src/Services/` | Recursos do Windows, dados e serviços do aplicativo |
| `src/Services/NativeCaptureService.cs` | Inicialização e encerramento do processo de captura |
| `src/Services/StreamService.cs` | Janelas dos visualizadores e fachada para captura |
| `src/Services/Updates/install_update.ps1` | Script incorporado ao assembly e extraído para aplicar atualizações |
| `src/CaptureWorker/` | Projeto separado para Windows Graphics Capture |
| `frontend/src/App.tsx` | Escolha entre aplicativo principal e visualizador |
| `frontend/src/AppRoutes.tsx` | Renderização das abas |
| `frontend/src/layout/` | Moldura, navegação e barra de título |
| `frontend/src/hooks/` | Estado do aplicativo, auto-hide e notificações |
| `frontend/src/features/` | Dashboard, WuWa, cloud, gestos, configurações, skins e transmissão |
| `frontend/src/features/stream/peerConfig.ts` | Configuração PeerJS compartilhada por host e viewer |
| `frontend/src/components/` | Componentes compartilhados |
| `frontend/src/styles/` | Estilos separados por área |
| `frontend/src/index.css` | Entrada CSS; ordem explícita dos módulos |
| `frontend/src/webview.d.ts` | Tipos da ponte C# e callbacks nativos |
| `frontend/watch.html` | Visualizador web independente |
| `cloudflare_pages/` | Instruções e dist gerado para hospedagem externa |
| `wwwroot/` | Saída do Vite e skins; não editar os bundles manualmente |
| `assets/defaults/` | Modelos públicos opcionais para releases |
| `Data/` | Configurações pessoais; nunca fonte de empacotamento |
| `scripts/lib/ReleaseValidation.ps1` | Validação de frontend, pacote e caminhos de limpeza |
| `scripts/tests/test_release.ps1` | Testes isolados de pacote e cópia de atualização |

## Contratos a preservar

- Cada aba mantém seu componente. O roteamento monta a aba
  selecionada, exceto a transmissão, que permanece montada para preservar a sala.
- Os módulos CSS são importados na ordem original. Não reordene imports sem
  verificar a cascata, incluindo estilos do visualizador.
- O TypeScript está em modo `strict`. Novos métodos nativos devem constar em
  `webview.d.ts`; o protocolo de salas é validado em `features/stream/protocol.ts`.
- Erros gerais e falhas da ponte usam `AppLog`; serviços também mantêm seus
  logs específicos. O logger não deve impedir o encerramento do aplicativo.
- `StreamService` mantém a fachada pública da captura. `NativeCaptureService`
  controla o processo auxiliar; o pipeline de mídia permanece nos módulos existentes.

## Build, distribuição e atualização

Use `scripts/run_dev.ps1` para compilar e abrir um build local. Veja
[TESTING.md](TESTING.md) para o roteiro e o isolamento de configurações.

A versão oficial é `<Version>` em `Xennex.csproj`. O empacotador lê esse valor e
rejeita `-Version` divergente. Os metadados do aplicativo derivam dessa propriedade,
e o publish do worker recebe a mesma versão.

Para distribuição, use exclusivamente `scripts/package_release.ps1`.
Os dois executáveis são publicados self-contained para win-x64. `wwwroot/`,
`WebView2Loader.dll`, dados padrões e scripts ficam ao lado deles no pacote;
não estão todos embutidos em um único executável.

Somente a skin `default` é distribuída. Templates de dados vêm de
`assets/defaults/`, nunca de `Data/`. O atualizador preserva arquivos existentes
em `Data/` e ignora skins recebidas que não sejam `default`.

O WebView2 Runtime é externo. Gestos ainda requerem Python e suas bibliotecas;
REAL requer seu executável. A organização do código não empacota essas dependências.

Regras: [CODING_RULES.md](CODING_RULES.md), [AGENTS.md](../AGENTS.md) e
[release-packaging.md](../.agents/rules/release-packaging.md).

Streaming v0.2: consulte [STREAMING.md](STREAMING.md) para arquitetura, limites e validação.

Salas v3: `RoomCoordinator.ts` é migrável; `RoomClient.ts` preserva os peers de mídia.
Cada participante publica um catálogo de fontes, com assinatura/áudio independentes.
