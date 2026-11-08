---
description: Protocolo obrigatório de testes determinísticos e validação contínua (CI) antes de concluir qualquer tarefa
scope: ["scripts/tests/**", "frontend/tests/**", "Xennex.csproj"]
trigger: "sempre antes de concluir e entregar qualquer alteração no repositório"
---

# Regra de Ouro dos Testes e Verificação (Verification Gate)

Nenhuma tarefa ou modificação é considerada concluída sem passar na verificação automatizada.

---

## 1. Princípio de Zero Regressões

Qualquer alteração feita por um desenvolvedor humano ou modelo de IA deve respeitar a suíte de testes existente. Se um teste falhar, investigar e registrar a causa antes de concluir: pode ser regressão, teste desatualizado ou ambiente indisponível. Não alterar expectativas apenas para fazê-lo passar, nem declarar sucesso se uma verificação necessária não foi executada.

---

## 2. A Bateria de Testes do Xennex

### A. Validação de CI Completa (C# + Python + Segurança)
Execute antes de finalizar qualquer lote de alterações:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_ci.ps1
```
Este script executa de forma determinística:
1. `SecurityTests.csproj`: verificações de loopback, tokens, CORS, path traversal e rejeição de updates forjados.
2. `SkinTests.csproj`: verificações de clonagem, preservação de propriedades e integridade de skins.
3. `GameAnalyticsTests.csproj`: verificações de esquemas, revisões e sessões.
4. `LocalAiTests.csproj`: verificações de orquestração de fila, orçamentos de RAM/VRAM e checkpoints.
5. `CompactTests.csproj --geometry-only`: verificações de cálculo físico multimonitor e bordas.
6. `GestureTests.csproj` e `test_gestures.py`: Validação de modelos de visão e supervisão do processo auxiliar sem abrir câmera física.
7. `test_release.ps1` e `test_update_security.ps1`: Integridade de pacotes e rejeição de payloads perigosos.

### B. Validação da Interface Web (Playwright)
Após rodar `npm run build` na pasta `frontend/`:
```powershell
powershell -ExecutionPolicy Bypass -Command "Set-Location 'frontend'; node tests/compact-ui.test.mjs"
```
Verifica viewport reduzido, navegação interna por módulos, retenção de rotas e transições.

### C. Compilação de Solução C#
Verifique se a compilação do C# não introduziu avisos ou quebras de contrato:
```powershell
dotnet build Xennex.csproj -c Release
```

---

## 3. Protocolo de Encerramento de Tarefas

1. Implemente o código necessário seguindo `coding-standards.md`.
2. Compile o frontend com `npm run build` (se houve alterações em `frontend/`).
3. Execute `test_ci.ps1` e os testes de interface correspondentes.
4. Certifique-se de que a saída terminou com código 0 (sucesso).
