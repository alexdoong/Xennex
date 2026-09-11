# Guia de Instalação e Execução - Xennex

Este documento descreve os passos para instalar, executar e preparar o ambiente de uso do **Xennex**.

---

## 🛠️ Requisitos de Sistema

| Componente | Requisito de Uso (Usuário) | Requisito de Desenvolvimento |
| :--- | :--- | :--- |
| **Sistema Operacional** | Windows 10 (64-bit) 1903+ ou Windows 11 | Windows 10 ou 11 (64-bit) |
| **Runtime .NET** | Não necessário (Self-Contained no ZIP) | .NET 8.0 SDK |
| **WebView2** | Microsoft Edge WebView2 Runtime | Microsoft Edge WebView2 Runtime |
| **Node.js** | Não necessário | Node.js 18+ e npm |
| **Privilégios** | Usuário padrão (Admin apenas p/ Wacom) | Usuário / Admin |

---

## 🚀 Como Executar o Xennex (Usuário Final)

O Xennex é distribuído em formato **portátil** (não necessita de instalador pesado):

1. **Baixar o Aplicativo**:
   - Vá até a aba [Releases do GitHub](https://github.com/alexdoong/Xennex/releases) e baixe o arquivo `Xennex-vX.Y.Z-win64.zip`.

2. **Extrair**:
   - Extraia o conteúdo do arquivo ZIP para uma pasta local segura (por exemplo: `C:\Users\SeuUsuario\AppData\Local\Xennex` ou `D:\Games\Xennex`).
   - *Evite extrair diretamente dentro de pastas protegidas como C:\Windows.*

3. **Executar**:
   - Dê dois cliques em **`Xennex.exe`**.
   - O aplicativo iniciará sua janela transparente e carregará a interface na bandeja do sistema.

---

## 🔒 Certificado Digital Oficial (`alexdoong`)

Para garantir a integridade dos executáveis e prevenir mensagens invasivas do Windows UAC / SmartScreen ("Fornecedor Desconhecido"):

1. Na pasta do Xennex extraído, localize o arquivo **`instalar_certificado_alexdoong.cmd`**.
2. Clique com o botão direito e selecione **"Executar como Administrador"**.
3. Uma confirmação será exibida e o certificado público oficial de `alexdoong` será registrado no repositório de autoridades confiáveis da sua máquina.
4. A partir desse momento, as caixas de diálogo do Windows exibirão com destaque em azul: **"Fornecedor verificado: alexdoong"**.

---

## 🌐 WebView2 Runtime

O Xennex utiliza o motor WebView2 da Microsoft para renderizar sua interface React de alta fidelidade:
- No Windows 11, o WebView2 Runtime já vem instalado de fábrica.
- No Windows 10, o próprio Windows Update costuma mantê-lo instalado.
- Se ao abrir o Xennex você receber uma mensagem informando que o WebView2 não foi encontrado, baixe o instalador oficial gratuito da Microsoft:  
  👉 [Download Microsoft Edge WebView2 Evergreen](https://developer.microsoft.com/microsoft-edge/webview2/)

---

## 🔄 Atualizações Automáticas

O aplicativo conta com sistema nativo de auto-atualização:
- Dentro do aplicativo, abra a aba **Configurações -> Atualizações**.
- Clique em **"Verificar Atualizações"**.
- Se houver uma nova versão disponível no GitHub, basta clicar em **"Instalar Atualização"**.
- O Xennex fará o download seguro em segundo plano e reiniciará automaticamente com a nova versão, **preservando integralmente** seus dados de configuração (`Data/config.txt`) e suas skins personalizadas em `wwwroot/skins/`.
