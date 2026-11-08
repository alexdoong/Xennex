---
description: Protocolo obrigatório para montagem, empacotamento, assinatura digital Authenticode e sanitização de releases portáteis
scope: ["scripts/package_release.ps1", "scripts/lib/ReleaseValidation.ps1", "Backup/**"]
trigger: "sempre que gerar, empacotar ou publicar uma nova versão ou release"
---

# Regra de Empacotamento de Releases e Higiene do Repositório ("Normie PC")

Esta regra define o protocolo obrigatório para montagem, empacotamento, versionamento e distribuição de novas versões do **Xennex** para amigos, testadores e usuários finais, sem burocracia e com máxima segurança de dados.

---

## Objetivo
Garantir que qualquer pacote distribuído funcione de primeira ("out-of-the-box") em qualquer computador com Windows 10/11, sem exigir instalação prévia de .NET SDK, Node.js ou ferramentas de desenvolvedor, sem telas pretas/invisíveis por falta de assets e **sem nenhum vazamento de dados de usuário ou configurações locais**.

---

## Diretrizes Obrigatórias de Empacotamento

### 1. Integridade do Frontend (React + Vite)
- Antes de gerar qualquer executável de distribuição, a interface React deve ser compilada via `npm run build`.
- **Verificação Crítica**: É obrigatório checar se o arquivo JavaScript principal (`wwwroot/assets/index-*.js`) e os estilos (`index-*.css`) foram gerados com sucesso dentro de `wwwroot/assets/`.
- Se o bundle JS estiver ausente, o empacotamento deve ser abortado imediatamente, pois o fundo transparente do app fará a janela abrir invisível se o React não iniciar.

### 2. Compilação .NET Self-Contained (Win-x64)
- O executável deve **sempre** ser publicado em modo **Self-Contained** com inclusão de bibliotecas nativas:
  ```powershell
  dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o <caminho_staging>
  ```
- O executável auxiliar `Xennex.CaptureWorker.exe` também deve ser publicado no mesmo diretório de staging em modo Self-Contained.

### 3. Dependências Nativas & WebView2
- O arquivo `WebView2Loader.dll` deve ser copiado diretamente para a raiz da pasta de distribuição, ao lado do `Xennex.exe`.
- O certificado público oficial (`alexdoong.cer`) e o script `instalar_certificado_alexdoong.cmd` devem ser incluídos na raiz do pacote.

### 4. Sanitização Estrita de Dados (Whitelist em Data/)
- **Proibição Absoluta de Cópia Cega:** A pasta `Data/` do pacote de distribuição NUNCA deve copiar arquivos indiscriminadamente do diretório local de desenvolvimento.
- **Whitelist Permitida:** Somente arquivos explicitamente aprovados podem entrar em `Data/`:
  - `config.txt` (gerado do zero com caminhos limpos/neutros).
  - Modelos públicos: `gestures.json`, `swipe_config.json`, `team_config.txt`, obtidos somente de `assets/defaults/` (opcionais).
- **Bloqueio Obrigatório:** Arquivos como `wuwa_build.txt`, dados de conta, logs (`*.log`, `*_log.txt`, `*.txt` que contenham logs) e tokens jamais podem entrar no pacote.

### 5. Preservação de Dados do Usuário na Atualização
- O instalador / atualizador (`src/Services/Updates/install_update.ps1`) deve respeitar os dados existentes no computador do usuário:
  - Nunca sobrescrever arquivos existentes na pasta `Data/` (ex: `config.txt`, builds, tokens).
  - Nunca deletar nem substituir pastas de skins personalizadas criadas pelo usuário dentro de `wwwroot/skins/`.

### 6. Fonte Única da Verdade para Versão & Tags Git
- A versão oficial do aplicativo reside exclusivamente em `Xennex.csproj` na tag `<Version>X.Y.Z</Version>`.
- O código C# (`UpdateService.cs`) e o script de empacotamento obtêm essa versão dinamicamente via metadados do Assembly / XML do projeto. Nunca use versões fixas ("hardcoded") em arquivos C#.
- **Padrão de Tags Git:** Todas as novas tags no Git devem seguir o padrão estrito:
  - `v0.2.3`, `v0.2.4`, etc. (prefixo `v` minúsculo seguido por Major.Minor.Patch).
  - Evite variações como `V0.1`, `v.0.2.1`.

### 7. Estrutura Padrão de Arquivos do Pacote Portátil
Todo arquivo `.zip` ou pasta de release deve conter estritamente:
```
Xennex-vX.Y.Z-win64/
├── Xennex.exe                      # Executável principal assinado por alexdoong
├── Xennex.CaptureWorker.exe        # Motor de captura GPU assinado
├── Xennex.GesturesWorker.exe       # Worker de gestos com runtime/modelos empacotados
├── WebView2Loader.dll              # Carregador nativo do Edge WebView2
├── alexdoong.cer                   # Certificado público Authenticode
├── instalar_certificado_alexdoong.cmd # Instalador de 1 clique do certificado
├── wwwroot/                        # Interface visual completa (HTML, assets JS/CSS, skins)
│   └── skins/default/              # Apenas a skin padrão limpa (sem duplicações)
├── Data/                           # Configurações padrão limpas da whitelist
└── scripts/                        # Scripts Python e auxiliares (hand_motion.py)
```

### 8. Empacotador obrigatório e integridade da cópia

Use exclusivamente `powershell -ExecutionPolicy Bypass -File scripts/package_release.ps1`.
O parâmetro opcional `-Version` deve coincidir com `<Version>` no projeto.
O script valida, assina e gera `Backup/Xennex-vX.Y.Z-win64.zip`; não publica a release.

Ao copiar a interface após publish, valide o destino dentro do staging, remova
a pasta wwwroot gerada ali, recrie-a e copie **seu conteúdo**. Copiar a pasta
para outra wwwroot existente causa aninhamento wwwroot/wwwroot.
Valide que esse aninhamento não existe e que o JS referenciado pelo index.html
existe e tem mais de 50 KB, além do CSS. Falha deve abortar o pacote.
Use scripts/lib/ReleaseValidation.ps1 e scripts/tests/test_release.ps1.

Assinatura usa o certificado configurado e fingerprint público existente.
Não gerar nova chave silenciosamente nem distribuir a chave privada.
O pacote exige WebView2 Runtime instalado/disponível no Windows; o loader
sozinho não é o runtime. Não prometer funcionamento sem esse pré-requisito.

### 9. Checklist de Higiene Pré-Commit
Antes de commitar novas alterações:
```bash
# 1. Conferir arquivos modificados e adicionados
git status

# 2. Ver quais arquivos estão staged para commit
git diff --cached --name-status

# 3. Garantir que arquivos ignorados não estão sendo rastreados
git ls-files --cached --ignored --exclude-standard
```
*(Se algum arquivo ignorado aparecer no comando acima, utilize `git rm --cached <arquivo>` para retirá-lo do rastreamento).*
