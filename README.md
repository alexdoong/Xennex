# Xennex

> **HUD Gamer, Central de Utilitários e Transmissão de Alta Performance para Windows**  
> Desenvolvido em **.NET 8 (WPF / WebView2)** com interface moderna em **React + TypeScript**.

[![Platform](https://img.shields.io/badge/Plataforma-Windows%2010%20%2F%2011%20(64--bit)-blue.svg)](#requisitos-do-sistema)
[![.NET](https://img.shields.io/badge/.NET-8.0--windows-purple.svg)](https://dotnet.microsoft.com/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite%20%2B%20TS-61dafb.svg)](frontend/)
[![License](https://img.shields.io/badge/Distribuidor-alexdoong-green.svg)](#distribuidor-oficial--certificado)

---

## 🌟 O que é o Xennex?

O **Xennex** é um aplicativo de ambiente pessoal (HUD overlay) projetado para jogadores, streamers e criadores de conteúdo no Windows. Ele combina uma interface translúcida em **Glassmorphism**, aceleração de hardware e ferramentas de baixa latência em um único painel leve, moderno e fluído.

---

## 🚀 Principais Funcionalidades

### 1. 📡 Transmissão P2P de Tela e Áudio (Live Stream)
- Compartilhamento de tela e janelas individuais direto via WebRTC / PeerJS com baixíssima latência.
- **Captura de Áudio Exclusiva por Processo**: Captura o áudio direto do jogo em execução via WASAPI / WinMM Loopback sem duplicar sons do sistema.
- **Motor GPU WGC Dedicado**: Aceleração via Windows Graphics Capture com processo isolado (`Xennex.CaptureWorker.exe`).
- **HUD Dinâmico**: Os controles flutuantes da transmissão ocultam automaticamente após inatividade do mouse e reaparecem instantaneamente ao movê-lo.

### 2. ✋ Hand Motion Tracking (Controle por Gestos)
- Rastreamento de mãos em tempo real via câmera para disparo de atalhos e macros virtuais sem precisar tirar a mão dos controles.
- Integração modular com pipeline de visão computacional em segundo plano.

### 3. 🎮 Wacom Tablet & REAL Audio Latency Controller
- Controle rápido de ativação/desativação dos drivers e serviços de hardware de mesas digitalizadoras Wacom.
- Gerenciamento integrado do motor de redução de latência de áudio (`REAL.exe`) sem deixar janelas pretas de terminal abertas.

### 4. 🎨 Motor Avançado de Skins & Glassmorphism
- Customização visual profunda: fundos dinâmicos por imagem ou vídeo, ajustes em tempo real de opacidade, desfoque (blur), paleta de cores e bordas.
- Editor integrado de skins com suporte a exportação, importação e isolamento para que temas customizados nunca sejam perdidos em atualizações.

### 5. 🪟 Interface Fluida & Redimensionamento Livre
- Janela com suporte total à transparência nativa do Windows.
- Redimensionamento livre em qualquer proporção com cantos inteligentes e adaptação automática de grids sem cortes de conteúdo.

### 6. 🔄 Atualizador Automático & Assinatura Digital
- Verificação de novas versões integrada ao GitHub Releases com download em stream direto.
- Atualização em segundo plano que preserva dados locais de configuração (`Data/`) e skins criadas pelo usuário.
- Binários assinados digitalmente com a identidade oficial de **`alexdoong`**.

---

## 💻 Requisitos do Sistema

### Para Usuários Finais (Executar o App):
- **Sistema Operacional:** Windows 10 (64-bit) versão 1903+ ou Windows 11.
- **WebView2 Runtime:** Já incluso nativamente no Windows 11 e na maioria dos Windows 10 atualizados. *(Caso não possua, o instalador gratuito da Microsoft está disponível em [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)).*
- **Pacote Portátil:** As versões de release são distribuídas no formato **Self-Contained** (já incluem todas as dependências do .NET necessárias).

### Para Desenvolvedores (Compilar o Projeto):
- **.NET 8.0 SDK** (x64)
- **Node.js** v18+ e **npm**
- **PowerShell** 5.1+

---

## 📥 Como Usar

1. Acesse a aba de [Releases](https://github.com/alexdoong/Xennex/releases) do repositório.
2. Baixe o pacote mais recente: `Xennex-vX.Y.Z-win64.zip`.
3. Extraia o arquivo ZIP para uma pasta de sua preferência (ex: `C:\Programas\Xennex`).
4. Execute o **`Xennex.exe`**.
5. *(Opcional)* Para validar o fornecedor oficial e evitar alertas do Windows SmartScreen, clique com o botão direito em `instalar_certificado_alexdoong.cmd` e execute como Administrador.

---

## 🛠️ Como Compilar o Projeto

Se você deseja contribuir ou compilar a partir do código-fonte:

```bash
# 1. Clonar o repositório
git clone https://github.com/alexdoong/Xennex.git
cd Xennex

# 2. Instalar dependências e compilar o Frontend React
cd frontend
npm install
npm run build
cd ..

# 3. Compilar a solução .NET 8 (Modo Debug ou Release)
dotnet build Xennex.csproj -c Release

# 4. Executar em desenvolvimento
dotnet run --project Xennex.csproj
```

### Gerando o Pacote de Distribuição Portátil ("Normie PC")
Para compilar o frontend, gerar o binário Self-Contained, aplicar a assinatura digital de `alexdoong` e empacotar o ZIP pronto para distribuição:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_release.ps1
```

O arquivo final será gerado em `Backup/Xennex-vX.Y.Z-win64.zip`.

---

## 📜 Histórico e Marco Zero

<details>
<summary>Clique para ver a memória histórica do primeiro protótipo ("Marco Zero")</summary>

Este repositório registra o Marco Zero Absoluto de todo o projeto. O código inicial refletiu a primeira coisa real e física que foi realizada: um rascunho funcional e bruto feito para centralizar automações que antes ficavam espalhadas em arquivos soltos.

É um protótipo experimental, focado puramente em validar a ideia e ver o dashboard funcionando na prática pela primeira vez.

O que aquele primeiro código fazia:
1. Controle dos Drivers Wacom: Disparava arquivos .bat para ativar/desativar os serviços de hardware direto pela interface.
2. Esconder o REAL.exe: Inicializava o motor de redução de latência de áudio em segundo plano capturando linhas de texto em log interno.
3. Compilação arcaica via csc.exe nativo do Windows.

Hoje o Xennex evoluiu para uma arquitetura moderna em .NET 8 WPF com interface reativa em React, mas essa raiz de automação prática e foco em produtividade permanece no DNA do projeto.
</details>
