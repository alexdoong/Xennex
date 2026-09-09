# Regra de Empacotamento de Releases para Usuários Finais ("Normie PC")

Esta regra define o protocolo obrigatório para montagem, empacotamento e distribuição de novas versões do **Xennex** para amigos, testadores e usuários finais.

---

## Objetivo
Garantir que qualquer pacote distribuído funcione de primeira ("out-of-the-box") em qualquer computador com Windows 10/11, sem exigir instalação prévia de .NET SDK, Node.js ou ferramentas de desenvolvedor, e sem causar telas pretas ou transparentes por falta de assets.

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
- Isso embute o .NET 8 Runtime dentro do próprio `Xennex.exe` (~150-160 MB), garantindo que usuários que não tenham o .NET 8 instalado consigam rodar sem erros.

### 3. Dependências Nativas & WebView2
- O arquivo `WebView2Loader.dll` deve ser copiado diretamente para a raiz da pasta de distribuição, ao lado do `Xennex.exe`.
- Isso garante que o WebView2 encontre o loader nativo em qualquer máquina Windows.

### 4. Estrutura Padrão de Arquivos do Pacote Portátil
Todo arquivo `.zip` ou pasta de release deve conter estritamente:
```
Xennex-vX.Y.Z-win64/
├── Xennex.exe              # Executável compilado com metadados e ícone oficial
├── WebView2Loader.dll      # Carregador nativo do Edge WebView2
├── wwwroot/                # Interface visual completa (HTML, assets JS/CSS, skins, data)
├── Data/                   # Configurações padrão limpas (sem caminhos locais de dev)
└── scripts/                # Scripts Python complementares (hand_motion.py)
```

### 5. Higienização de Dados Locais
- A pasta `Data/` de distribuição **nunca** deve conter caminhos absolutos locais da máquina de desenvolvimento (ex: `E:\Projetos e apps\...`).
- O arquivo `Data/config.txt` deve apontar para caminhos relativos ou vazios para acionar a auto-detecção no PC do usuário.
- Arquivos de log (`*.log`) e arquivos de debug (`*.pdb`) devem ser excluídos do pacote.

### 6. Automação Padronizada
- Para gerar uma nova release sem erros manuais, utilize sempre o script automatizado:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/package_release.ps1 -Version "X.Y.Z"
  ```
- O script realiza todas as validações de integridade, compilação, assinatura e compactação em `Backup/Xennex-vX.Y.Z-win64.zip`.

### 7. Prevenção de Aninhamento Indevido (PowerShell Copy-Item Gotcha)
- No PowerShell, quando o `dotnet publish` já cria a pasta `wwwroot` no diretório de destino, executar `Copy-Item -Recurse -Path $wwwroot -Destination $dest\wwwroot` faz o PowerShell criar uma subpasta aninhada `wwwroot\wwwroot`!
- Isso faz com que a pasta `wwwroot` raiz fique sem o arquivo JavaScript novo, quebrando o carregamento da interface.
- **Regra**: O script de empacotamento deve SEMPRE excluir qualquer `wwwroot` gerado previamente pelo `dotnet publish`, criar a pasta limpa e copiar o conteúdo com `Copy-Item -Path "$wwwroot\*" -Destination "$dest\wwwroot\"`.
- É obrigatório validar programaticamente que `wwwroot\wwwroot` NÃO existe e que o arquivo JS referenciado pelo `index.html` existe e possui tamanho > 50 KB no pacote final.
