# Xennex - Arquitetura e Contexto

## 1. Visão Geral
O Xennex é um utilitário focado em performance, atalhos e automações para osu!, Wuthering Waves (WuWa) e sistema em geral (Wacom, áudio, processos).
O aplicativo passou por uma metamorfose de WinForms (Legado) para uma **Arquitetura Híbrida Web/C#**.

## 2. A Arquitetura Híbrida
A arquitetura separa completamente o **Motor/Backend** (C#) do **Visual/Frontend** (Web com React).
- **Backend (C# / .NET 8):** Gerencia tudo que fala com o Windows (Processos, Arquivos, Wacom, REAL Engine).
- **Frontend (React + Vite + TypeScript):** Toda a interface é desenhada usando componentes React e tipagem estrita (TS). O build do Vite gera os arquivos estáticos na pasta `wwwroot`, e roda dentro de um controle WebView2 hospedado no WPF.

### 2.1. O "Aquário" (MainWindow.xaml)
- A `MainWindow.xaml` atua como um "aquário" para o site. Ela tem bordas invisíveis (`WindowStyle="None"`) e utiliza um truque da Win32 API (`WS_EX_LAYERED` com `ColorKey` Magenta) para permitir cantos arredondados e transparência real, sem o infame bug de cliques no WebView2.
- O WebView2 aponta nativamente para a pasta `wwwroot`.

### 2.2. A Ponte (Interop)
O Frontend e o Backend se comunicam via a classe `ApiBridge.cs`.
- No C#, registramos o bridge: `webView.CoreWebView2.AddHostObjectToScript("api", apiBridge);`
- No TypeScript, declaramos os tipos globais em `webview.d.ts` e chamamos o C# usando: `window.chrome.webview.hostObjects.api.Metodo()`.
- O Bridge deve ser extremamente simples e apenas delegar ações para os `Services` do C#.

## 3. Estrutura de Pastas
- `src/` -> Contém todo o código C# (Motor), utilizando o namespace `Xennex` e `Xennex.Services`.
  - `Interop/` -> Classes de comunicação (ex: `ApiBridge.cs`).
  - `Models/` -> Classes de Dados.
  - `Services/` -> Lógica pesada e isolada (ex: `WacomService.cs`, `ConfigService.cs`).
  - `UI/` -> Janela WPF hospedeira (`MainWindow.xaml`).
- `frontend/` -> Código fonte da UI em React + TypeScript. Utilize `npm run build` aqui para compilar a interface.
- `wwwroot/` -> Pasta destino onde o Vite joga os arquivos compilados (HTML/CSS/JS). NENHUM código C# ou código fonte React existe aqui, apenas o bundle de produção.
- `Data/` -> Arquivos de configuração e dados locais do usuário (`config.txt`, `.json`, etc).
- `docs/` -> Documentação e guias de contexto do Agente.

## 4. O Sistema de Compilação (Single-File)
A compilação do projeto utiliza o comando de `publish` do .NET para gerar um **Único Arquivo Executável** contendo tudo (inclusive as dependências do WebView2 e os arquivos do `wwwroot`).
- Comando de Build Completo: `dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true`
- O arquivo `.csproj` foi limpo para não gerar lixo na raiz do projeto durante builds normais.
