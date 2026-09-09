# Regras de Programação (Clean Code / Boas Práticas)

Para manter o projeto organizado, sem lixo e escalável, qualquer agente (IA) ou programador deve seguir **estritamente** estas regras:

## 1. Responsabilidade Única (SOLID)
- Nenhuma classe C# deve fazer duas coisas.
- O `MainWindow.xaml.cs` **não pode ter lógica de negócios**. Ele serve apenas para segurar o WebView2 e fazer ajustes relacionados ao Window do Windows.
- O `ApiBridge.cs` **não processa nada**. Ele apenas age como um despachante de comandos entre Javascript e os `Services`.
- Cada grande feature tem que ter seu arquivo de `Service` próprio em `src/Services/` (ex: `WacomService`, `WuWaService`, `RealEngineService`).

## 2. A Camada Visual usa React e TypeScript (Frontend Moderno)
- O frontend em `frontend/` (compilado para `wwwroot/`) não toma decisões complexas de OS. Ele aciona eventos no backend (`window.chrome.webview.hostObjects.api`) ou reage a dados.
- **Tipagem Estrita:** Todo código frontend DEVE ser escrito em TypeScript. Qualquer chamada ao backend deve estar documentada e tipada no `webview.d.ts`.
- **Componentização:** Use o React de forma modular. Telas, modais e abas grandes devem ser componentes separados (`.tsx`).
- **Design Premium:** Sempre foque em uma estética limpa, com Dark Mode, Glassmorphism e transições suaves. Use CSS moderno e mantenha o `index.css` limpo.

## 3. Tolerância a Falhas e Logs
- Processos do Windows (`Process.Start`, `Process.Kill`) frequentemente dão `AccessDenied` ou não encontram o arquivo. TODO método que interage com processos do OS ou Sistema de Arquivos deve estar dentro de um bloco `try-catch` apropriado.
- Exiba mensagens visíveis no console/log interno caso ocorra falha.

## 4. Sem lixo no Git
- O Github deve sempre estar perfeitamente limpo, subindo APENAS código fonte.
- NUNCA commite `.exe`, `.dll`, arquivos do `.vs/`, ou as pastas `bin/` e `obj/`.
- Os arquivos do sistema de build `.deps.json`, `runtimeconfig.json` e a pasta `runtimes/` também devem ser ignorados.
- Arquivos de configuração pessoal do usuário (`config.txt`, `.agent-docs`, `wuwa_build.txt`) DEVEM estar no `.gitignore`.

## 5. Estrutura de Pastas e Separação Lógica
- Sempre que um novo código, funcionalidade ou contexto se tornar grande o suficiente a ponto de poluir uma pasta existente, **crie uma nova pasta** com um nome claro e auto-explicativo.
- A ideia é que se alguém que nunca viu o projeto abrir o código fonte, a pessoa deve conseguir navegar pelas pastas e entender exatamente onde cada peça do aplicativo mora, sem precisar adivinhar.

## 6. Código Plano (Evite o Código "Flecha" / Deep Nesting)
- Evite ao máximo alinhar condicionais dentro de condicionais (`if` dentro de `for` dentro de `if` dentro de `if`). O código não pode parecer uma flecha deitada `(> ...)`.
- **Early Returns (Cláusulas de Guarda):** Em vez de encapsular todo o bloco de sucesso num `if`, verifique o erro primeiro e dê `return` imediatamente.
- *Código raso é código legível:* Ninguém deve precisar manter na cabeça o que aconteceu 3 níveis de código acima para entender a linha atual.

## 7. Isolamento de Abas e Padronização UI (Frontend)
Para não transformar o Frontend num monstro indomável:
- **Componentização Estrita:** Cada nova aba DEVE ser um componente isolado (`NomeDaAbaTab.tsx`). O arquivo `App.tsx` serve apenas como roteador para ligar/desligar abas.
- **Separação de CSS (Scoping):** Toda aba deve ter um contêiner principal com um ID ou Classe única (Ex: `<div className="tab-content wuwa-tab">`). No `index.css`, as regras específicas da aba DEVEM ser aninhadas dentro da classe pai (Ex: `.wuwa-tab h2 { ... }`).
- **Reaproveitamento UI:** Regras globais (ex: `.btn`, painéis de vidro `.glass-panel`) devem ser criadas na raiz do `index.css` e reaproveitadas em todas as abas. Nenhuma aba deve recriar botões ou estilos base do zero.
- **Isolamento de Layout:** Nenhuma aba deve intervir no `Titlebar` ou no `topbar`. O conteúdo da aba se restringe a viver abaixo da barra superior de navegação.

