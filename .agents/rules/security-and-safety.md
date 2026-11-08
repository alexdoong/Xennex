---
description: Regras invioláveis de segurança, loopback 127.0.0.1, autenticação de sockets por token, sanitização de caminhos e preservação de Data/ e skins
scope: ["src/Services/LocalWebServer.cs", "src/Services/Security/**", "src/Interop/**", "Data/**"]
trigger: "sempre que manipular rede, sockets, caminhos de arquivo, persistência ou skins"
---

# Regras Invioláveis de Segurança e Integridade (Security & Safety)

Este documento define os limites de segurança estritos do **Xennex**. Nenhuma IA (seja local ou gerente) tem permissão de enfraquecer essas restrições.

---

## 1. Segurança de Rede e Sockets Locais

- **Restrição Estrita a Loopback**: Qualquer servidor local (HTTP, WebSocket, áudio, streaming) deve escutar EXCLUSIVAMENTE em `127.0.0.1` ou `localhost`. NUNCA associe a `0.0.0.0` ou IPs de interface externa.
- **Autenticação Obrigatória por Token**:
  - Todo WebSocket local exposto pelo `LocalWebServer` exige um token criptográfico aleatório de 256 bits gerado por sessão.
  - O token só é transmitido à interface através do canal seguro em memória do `ApiBridge`. Clientes que conectarem sem token ou com token inválido devem ser rejeitados imediatamente.
- **Origem (CORS e WebView2)**:
  - Não use wildcard `*` no CORS. Apenas a origem segura do app é aceita.
  - Bloqueie navegações externas dentro da janela privilegiada do app. Links externos (`http://`, `https://`) devem ser abertos no navegador padrão do sistema operacional (`Process.Start`).

---

## 2. Integridade de Dados Pessoais e Configurações

- **Preservação de `Data/`**:
  - Nenhuma atualização, refatoração de serviço ou teste pode excluir ou sobrescrever arquivos de configuração do usuário em `Data/` sem migração retrocompatível declarada.
  - Novos campos em `AppConfig.cs` devem conter valores padrão retrocompatíveis com versões anteriores de `Data/config.txt`.
- **Preservação de Skins do Usuário**:
  - O atualizador e o código de distribuição distribuem exclusivamente a skin `default`.
  - Skins personalizadas criadas pelo usuário (ex: `Denia`) NUNCA podem ser excluídas, sobrescritas ou alteradas automaticamente.

---

## 3. Segurança do Sistema de Arquivos (Path Traversal)

- **Sanitização Rigorosa de Caminhos**:
  - Ao carregar assets, skins ou rotas públicas, valide sempre contra Directory Traversal (`..`, `/`, `\`, nomes reservados do Windows como `CON`, `PRN`, `AUX`, `NUL`).
  - Caminhos devem ser normalizados (`Path.GetFullPath`) e comparados para garantir que permaneçam dentro do diretório permitido (`rootPath`).

---

## 4. Segurança do Atualizador e Binários

- **Validação de Atualizações**:
  - O atualizador só aceita pacotes ZIP da release oficial assinada no GitHub.
  - Exige correspondência exata do hash SHA-256 e tamanho de arquivo.
  - NUNCA execute arquivos arbitrários enviados via interface web ou comandos não autenticados.
- **Assinatura Digital**:
  - Executáveis de release (`Xennex.exe`, `Xennex.CaptureWorker.exe`, `Xennex.GesturesWorker.exe`) devem ser validados quanto à assinatura Authenticode com o certificado oficial (`assets/publisher-thumbprint.txt`).
