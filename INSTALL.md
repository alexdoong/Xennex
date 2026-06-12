# Guia de Instalação e Configuração - Xennex

Este documento contém as instruções para preparar o ambiente, compilar o Xennex e estruturar um futuro instalador para o programa.

---

## 🛠️ Requisitos do Sistema

Para executar e compilar o Xennex, o sistema precisa de:

1. **Windows 10 ou 11 (64-bit)**
2. **.NET Framework 4.8 Runtime** (para executar) / **.NET SDK 8.0+** (para compilar)
3. **Drivers Wacom** instalados (caso queira usar o gerenciamento de drivers)
4. **REAL.exe** (Reduce Audio Latency) - Opcional, mas necessário para a redução de latência de áudio.

---

## 💻 Instalação Manual & Desenvolvimento

### 1. Instalar o .NET SDK (Compilador)
Se você não tem o SDK do .NET instalado, pode instalá-lo rapidamente pelo terminal (CMD/PowerShell) com o comando:
```cmd
winget install Microsoft.DotNet.SDK.8
```

### 2. Compilação
Com o SDK instalado, abra a pasta do projeto e execute o script:
```cmd
compile.bat
```
Isso gerará o executável `WacomRealController.exe` na raiz da pasta.

---

## 📦 Planejamento para o Instalador (Futuro)

Quando formos criar um instalador automatizado (usando ferramentas como Inno Setup, Wix Toolset ou um script customizado), o instalador deverá realizar os seguintes passos no computador do usuário final:

### 1. Arquivos Necessários para Empacotamento
O instalador deve copiar os seguintes arquivos para a pasta de destino (ex: `C:\Program Files\Xennex` ou `%LocalAppData%\Xennex`):
- `WacomRealController.exe` (O executável do painel)
- `DisableWacomDrivers.bat` (Script para desligar drivers)
- `EnableWacomDrivers.bat` (Script para ligar drivers)
- `REAL.exe` (Caso queira distribuir o motor de áudio junto)
- `config.txt` (Arquivo de configuração inicial)

### 2. Atalhos e Inicialização com o Windows
Para permitir a inicialização automática, o instalador pode criar uma chave no Registro do Windows:
- **Caminho**: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
- **Nome**: `Xennex`
- **Valor**: `"C:\Caminho\Para\WacomRealController.exe" --minimized` (se implementado argumento de início minimizado)

### 3. Permissões de Administrador (UAC)
Como o controle de drivers Wacom utiliza comandos do sistema que exigem privilégios elevados, o executável `WacomRealController.exe` possui um manifesto de aplicação que solicita privilégios de Administrador ao ser iniciado. O instalador deve garantir que seja instalado com as permissões corretas para não bloquear o funcionamento das ferramentas de hardware.
