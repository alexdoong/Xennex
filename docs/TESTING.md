# Validação local

## Abrir o código atualizado

Feche a instância antiga do Xennex antes de testar: o aplicativo permite uma
única instância e pode restaurar a antiga em vez de abrir o build novo.

Na raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_dev.ps1
```

O script compila a interface, o aplicativo e o CaptureWorker e abre
`bin/Release/net8.0-windows/Xennex.exe`. Use `-BuildOnly` para apenas compilar.
Este é um build de desenvolvimento e depende do .NET instalado. Para distribuir,
use exclusivamente `scripts/package_release.ps1`.

O executável antigo da raiz não é substituído pelo build de desenvolvimento.
As configurações deste build ficam em `bin/Release/net8.0-windows/Data/`;
os dados pessoais de `Data/` na raiz não são copiados nem modificados.
O frontend e as skins são copiados pelo build. O script de gestos e o `REAL.exe`
local, quando existente, também ficam disponíveis na saída de desenvolvimento.

## Roteiro manual

- Abrir o app, navegar por todas as abas, redimensionar e arrastar a janela.
- Ativar/desativar sidebar, mudar posição e testar auto-hide das duas barras.
- Trocar e editar skins, incluindo imagem, vídeo, bordas e cores.
- Fechar, minimizar à bandeja, restaurar e encerrar completamente.
- Iniciar/parar REAL e testar Wacom no ambiente com os drivers disponíveis.
- Testar câmera, gravação/exclusão de gestos e configuração de swipe.
- Abrir sala, transmitir janela/tela com áudio, entrar pelo visualizador e navegador.
- Parar/reiniciar a transmissão; abrir múltiplos visualizadores e encerrar o app.
- Consultar a versão e verificar atualizações. Não instalar uma release antiga
  sobre este build de teste para validar a organização do código.

Gestos ainda dependem do Python e das bibliotecas importadas em
`scripts/hand_motion.py` (OpenCV, MediaPipe, PyAutoGUI e NumPy).
O motor REAL e o WebView2 Runtime continuam sendo dependências externas.

## Verificações automatizadas

```powershell
cd frontend
npm run build
npm run lint
cd ..
dotnet build Xennex.csproj -c Release
dotnet build src/CaptureWorker/Xennex.CaptureWorker.csproj -c Release
powershell -ExecutionPolicy Bypass -File scripts/tests/test_release.ps1
```

O teste PowerShell cria fixtures dentro de `bin/`, verifica a integridade do
pacote e simula duas cópias de atualização. Não executa o atualizador completo,
não inicia processos de teste, não instala certificados e não toca nos dados reais.

Os testes não substituem a validação de captura, áudio, drivers, câmera,
renderização WebView2 e release assinada em um Windows limpo.
Falhas gerais do backend são registradas em `logs/xennex.log` ao lado do
executável; o atualizador registra falhas em `%TEMP%/xennex_update_error.log`.

## Streaming 0.2.x

Veja [STREAMING.md](STREAMING.md) para o build isolado, testes de salas e roteiro
de captura nativa, navegador e redes distintas.

A assinatura do pacote é verificada por WinVerifyTrust e pelo certificado esperado.
`scripts/tests/test_signature.ps1` valida assinatura íntegra, assinante incorreto e
adulteração usando arquivos temporários; exige o certificado local do projeto.
O empacotador aceita especificamente a raiz local não confiável, sem instalar
certificados no Windows, e rejeita as demais falhas de assinatura.
