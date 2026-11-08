---
description: Padrões de código, Clean Code, código plano, responsabilidade única e convenções C#/React/Python
scope: ["src/**", "frontend/src/**", "scripts/**"]
trigger: "sempre que escrever, modificar ou refatorar código"
---

# Regras de Padrão e Estrutura de Código (Coding Standards)

Este documento estabelece as convenções obrigatórias de engenharia de software para o **Xennex**. Modelos locais e gerentes de IA devem seguir estas diretrizes para manter o código limpo, previsível e sem regressões.

---

## 1. Princípios Gerais (Clean Code & Arquitetura)

### A. Responsabilidade Única (SOLID)
- Cada classe C# ou componente React possui uma única responsabilidade clara.
- **MainWindow.xaml.cs**: Gerenciamento da janela do Windows e hospedagem do WebView2. Nenhuma lógica de negócio de domínio (jogos, IA, áudio, streaming) deve ser inserida aqui.
- **ApiBridge.cs**: Despachante estritamente declarativo entre o JavaScript da WebView2 e os serviços C#. Não deve conter processamento de dados, cálculos pesados ou orquestração complexa.
- **src/Services/**: Onde mora a lógica de negócio (ex: `SidebarService`, `SkinService`, `StreamService`, `RealEngineService`).
- **Subpastas Especializadas**: Serviços complexos devem ser agrupados em namespaces próprios:
  - `src/Services/LocalAi/`
  - `src/Services/GameAnalytics/`
  - `src/Services/Gestures/`
  - `src/Services/Security/`
  - `src/Services/Updates/`

### B. Código Plano (Evite o Código "Flecha" / Deep Nesting)
- NUNCA empilhe condicionais aninhadas (`if` dentro de `for` dentro de `if` dentro de `while`).
- **Guard Clauses (Retornos Prematuros)**: Valide entradas, casos de erro e permissões logo no topo da função e execute `return` imediatamente.
- Mantenha funções concisas e focadas.

### C. Tratamento Defensivo de Erros e Logs
- Operações de sistema de arquivos, chamadas de processo (`Process.Start`, `Process.Kill`), sockets e interoperabilidade COM podem falhar por falta de permissão ou recursos indisponíveis.
- Sempre envolva essas operações em blocos `try-catch` apropriados.
- Registre erros no logger centralizado (`AppLog`) sem travar a interface do usuário nem mascarar falhas críticas.

---

## 2. Camada C# (.NET 8 WPF / Win32)

- **Tipagem e Nulabilidade**: Utilize tipos explícitos ou `var` com discernimento. Trate nulabilidades com cuidado (`?`, `??`).
- **Coordenadas Físicas vs DIPs**: O Windows opera em pixels físicos quando lida com chamadas nativas do Win32 (`SetWindowPos`, `GetWindowRect`, monitores múltiplos), mas o WPF opera em DIPs (Device-Independent Pixels). Qualquer serviço de janela (como `CompactDockGeometry` e `SidebarService`) deve calcular escalas físicas e de DPI separadamente para eixos X e Y.
- **Async/Await sem Bloqueio**: Utilize `async/await` com `Task` em operações de E/S ou rede. Evite `.Result` ou `.Wait()` para prevenir deadlocks na UI Thread.
- **Cancelamento Cooperativo (`CancellationToken`)**: Propague `CancellationToken` em operações longas (streaming de respostas de IA, captura de quadros, downloads de updates) para permitir cancelamento imediato sem deixar threads zumbis no Windows.
- **Gerenciamento de Recursos Não-Gerenciados (`IDisposable`)**: Handles do Win32, duplicações DXGI, bitmaps GDI e WebSockets devem ser liberados deterministamente via declarações `using` ou implementação estrita de `Dispose()`.

---

## 3. Camada Frontend (React + TypeScript + Vite)

- **TypeScript Strict**: Todo código novo DEVE ser fortemente tipado. Proibido o uso de `any` injustificado.
- **Sincronização Nativa (`webview.d.ts`)**: Sempre que um novo método for exposto no `ApiBridge.cs`, ele DEVE ser declarado e documentado em `frontend/src/webview.d.ts`.
- **Componentização Modular**:
  - `frontend/src/layout/`: Casca visual, navegação, barra de título e painel compacto.
  - `frontend/src/features/`: Módulos por área de funcionalidade (`stream`, `local-ai`, `games`, `hand-motion`, `cloud`, `settings`, `skins`).
  - `frontend/src/hooks/`: Hooks de ciclo de vida e estado centralizado.
- **Estabilidade de Referência da Ponte COM**:
  - Evite reler `window.chrome.webview.hostObjects.api` repetidamente como dependência de efeitos `useEffect`, o que pode causar re-renderizações cíclicas ou descarte de rascunhos em digitação.
  - Mantenha referências estáveis via hooks dedicados (`useAppState`).
- **Isolamento de Estado**:
  - Estado efêmero de UI deve residir no componente ou controller da feature. Quando compacto e janela completa editam o mesmo conteúdo, compartilhar rascunho e seleção no provider da feature para não perdê-los ao alternar a apresentação.
- **Escopo e Cascata de CSS**:
  - Nunca crie arquivos CSS órfãos sem importá-los na ordem correta em `frontend/src/index.css`.
  - Utilize escopo de classe pai para cada área (ex: `.compact-panel`, `.stream-workspace`, `.games-tab`).
  - Reaproveite tokens do sistema de design e classes utilitárias de `frontend/src/styles/base.css` (`.btn`, `.glass-panel`, `.title-btn`).

---

## 4. Camada Python (Gestures & AI Helpers)

- **Dependências Mínimas e Isoladas**: Dependências de Gestures ficam em `scripts/requirements-gestures.txt`. Auxiliares de IA devem declarar dependências próprias por recurso; não adicionar bibliotecas de IA ao ambiente de captura sem necessidade.
- **Processos Desacoplados**: Scripts Python comunicam-se com o C# via stdin/stdout com mensagens JSON padronizadas, sem criar dependências de runtime global no computador do usuário.
- **Testes Determinísticos**: Devem possuir scripts de teste que validem sintaxe e inicialização sem depender de câmera física conectada (`scripts/tests/test_gestures.py`).

---

## 5. Higiene do Repositório (Git)

- NUNCA submeta arquivos binários (`.exe`, `.dll`, `.pdb`), caches de compilação (`bin/`, `obj/`, `node_modules/`, `.venv/`) ou logs de execução (`*.log`).
- Arquivos em `Data/` (com dados pessoais ou tokens de teste) devem permanecer estritamente no `.gitignore`.
