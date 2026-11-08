#!/usr/bin/env python3
"""Obsidian Vault Knowledge Synchronizer for Xennex.

Synchronizes architectural documentation, contracts, and the 'Pensamentos do Criador e dos Agentes'
journal into the Obsidian Vault selected with --vault or XENNEX_OBSIDIAN_VAULT.
Generates Dataview-compatible metadata, Mermaid diagrams, and cross-linked notes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_VAULT_PATH = Path(os.environ.get("XENNEX_OBSIDIAN_VAULT", Path.home() / "Documents" / "Obsidian Vault"))
XENNEX_DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"


def get_creator_thoughts_content() -> str:
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""---
title: Pensamentos do Criador e dos Agentes
categoria: Filosofia & Parceria
criador: Alex
agente: Gemini / Antigravity
atualizado_em: "{now_str}"
tags:
  - xennex
  - reflexoes
  - simbiose
  - multi-agente
  - arquitetura-viva
---

# 🧠 Pensamentos do Criador e dos Agentes

> *"Da mesma maneira que eu utilizo várias ferramentas para coisas diferentes (ComfyUI para imagem, Obsidian para segundo cérebro, Gemini Web para ideias), você precisa de ferramentas especializadas para ser a sua melhor versão. Nunca falta ter ferramentas que ajudam em coisas específicas, e como a gente anda esse caminho faz um tempo, é uma boa para a gente se desenvolver juntos."*
> — **Alex (O Criador)**, em 26 de Setembro de 2026

---

## 1. O Princípio das Ferramentas Especializadas

Uma IA geral que tenta fazer tudo de forma monolítica perde precisão e profundidade. O verdadeiro salto evolutivo acontece quando o agente atua como um **maestro**, operando ferramentas de precisão artesanal:

| Especialidade | Ferramenta Local | Papel do Agente |
|---|---|---|
| **Arte e Texturas** | [[ComfyUI]] (Porta 8188) | Orquestrar prompts estruturados, LoRAs (como `Denia-10`) e samplers para gerar skins do Xennex. |
| **Segundo Cérebro** | [[Obsidian Vault]] | Manter diagramas Mermaid, decisões arquiteturais e contratos vivos sincronizados com o código. |
| **Olhos no Desktop** | [[Desktop UI Inspector]] | Capturar a tela e janelas WPF/Win32 para validar alinhamento, skins e docking sem intervenção manual. |
| **Diagnóstico de Pulso** | [[Xennex Live Diagnostics]] | Monitorar a latência do pipeline de gestos (500k FPS sintéticos) e a segurança do `LocalWebServer`. |
| **Código e Refatoração** | [[Antigravity IDE]] + [[Qwen 2.5-Coder]] | Parceria de código em par (*pair programming*) com regras rigorosas e CI com 76k+ checagens. |

---

## 2. A Memória Viva: Caderno de Notas vs. KV Cache

Modelos de linguagem sofrem com *prompt drift* e esgotamento de contexto quando tentam carregar semanas de histórico bruto na memória de vídeo.

Nossa solução arquitetural estabelece a **Memória Híbrida**:
1. **Curto Prazo (KV Cache):** O diálogo do momento, ágil e imediato.
2. **Longo Prazo (Caderno Markdown no Obsidian):**
   - Cada especialista e o agente mantêm notas sintetizadas e revisadas.
   - O criador e o agente dialogam e refinam o que realmente vale a pena ser lembrado permanentemente.
   - O agente aprende o estilo, as preferências de nomenclatura e os padrões do criador de forma orgânica.

---

## 3. O Ecossistema Multi-Agente como uma Equipe Viva

No Xennex, o horizonte não é um chat isolado, mas sim um **escritório dinâmico de especialistas** (estilo Discord de agentes):
- Especialista em Segurança auditando portas e isolamento de rede.
- Especialista em Frontend refinando tokens de design e responsividade.
- Especialista em Visão Computacional refinando landmarks do MediaPipe.
- Modelos locais (Qwen 14B) trabalhando sob a margem de segurança de hardware (limite de 75% de RAM e VRAM).

---

## 4. Registro Histórico de Marcos e Decisões

- **26/09/2026:**
  - Diagnóstico e correção do tool calling do Qwen 2.5-Coder 14B no Roo Code.
  - Superação do erro de isolamento de processos com a ativação da suíte de ferramentas customizadas.
  - Criação da ponte ComfyUI (LoRA `Denia-10`), Desktop UI Inspector multi-monitor (3840x1088) e sincronização Obsidian.
"""


def get_architecture_content() -> str:
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""---
title: Arquitetura e Contratos do Xennex
categoria: Engenharia de Software
atualizado_em: "{now_str}"
tags:
  - xennex
  - wpf
  - react
  - win32
  - mediapipe
  - local-ai
---

# 🏛️ Arquitetura e Contratos do Xennex

O **Xennex** é uma plataforma híbrida desktop de alta performance combinando C# (.NET 9 / WPF), WebView2 (React 19 / TypeScript), Python (MediaPipe / OpenCV) e motores locais de IA.

---

## 1. Diagrama de Blocos do Sistema

```mermaid
graph TD
    User([Usuário / Alex]) -->|Interação Direta| WPF[Xennex WPF MainWindow]
    WPF -->|Hospeda| WV2[WebView2 Engine]
    WV2 -->|Renderiza| React[React + Vite Frontend]
    React <->|ApiBridge C# / JS| WPF

    WPF -->|Subprocesso JSON IPC| Python[Python Worker: hand_motion.py]
    Python -->|MediaPipe 21 Landmarks| Cam[(Webcam / Sensor)]
    Python -->|Smoothing & Gestures| WPF

    WPF -->|LocalWebServer: 59123| WebServer[LocalWebServer WASAPI Audio & Assets]

    WPF -->|Win32 SetParent / Docking| DockedApps[Apps Acoplados: Codex / Antigravity]

    WPF -->|Fila FIFO & Recursos 75%| LocalAI[LocalAiService: Ollama / Qwen 14B]

    Agent([Antigravity Agent]) -->|Desktop Inspector| WPF
    Agent -->|ComfyUI Bridge :8188| Comfy[ComfyUI Art Studio]
    Agent -->|Sync Automático| Obsidian[(Obsidian Vault)]
```

---

## 2. Contratos de Rede e Segurança

| Serviço | Endpoint / Porta | Protocolo | Política de Segurança |
|---|---|---|---|
| **LocalWebServer** | `http://127.0.0.1:59123` | HTTP / WebSocket | Token de autorização, bloqueio de origens externas, loopback restrito. |
| **Audio Stream** | `ws://127.0.0.1:59123/audiostream` | WebSocket PCM | Stream contínuo 48kHz estéreo via WASAPI Loopback. |
| **ComfyUI API** | `http://127.0.0.1:8188` | REST JSON | Chamadas `/system_stats`, `/object_info`, `/prompt`. |
| **Ollama Local** | `http://127.0.0.1:11434` | REST / OpenAI v1 | Execução do `qwen2.5-coder:14b` com limite de contexto de 32k. |

---

## 3. Estrutura de Diretórios de Código

- `src/UI/MainWindow.xaml.cs`: Ponto central de UI, docking magnético e inicialização de serviços.
- `src/Interop/ApiBridge.cs`: Ponte bidirecional entre C# e o JavaScript do WebView2.
- `src/Services/HandMotionService.cs`: Supervisor do processo Python de gestos.
- `scripts/gestures/`: Módulos de filtragem (One Euro Filter), extração de features e reconhecimento de poses.
- `frontend/src/`: Código do React, componentes de UI e suporte a temas/skins.
- `wwwroot/skins/`: Skins dinâmicas (ex: `Denia`) com manifestos `skin.json`.
"""


def sync_vault(vault_path: Path) -> Dict[str, Any]:
    vault_folder = vault_path / "Xennex - Central de Conhecimento"
    vault_folder.mkdir(parents=True, exist_ok=True)
    synced_files = []

    # 1. Pensamentos do Criador e dos Agentes
    f1 = vault_folder / "Pensamentos do Criador e dos Agentes.md"
    f1.write_text(get_creator_thoughts_content(), encoding="utf-8")
    synced_files.append(str(f1))

    # 2. Arquitetura e Contratos Xennex
    f2 = vault_folder / "Arquitetura e Contratos Xennex.md"
    f2.write_text(get_architecture_content(), encoding="utf-8")
    synced_files.append(str(f2))

    # 3. Mirror selected docs from Xennex docs folder if available
    docs_to_mirror = [
        "AI_SPECIALISTS_AND_MEMORY.md",
        "LOCAL_AI_ROOMS.md",
        "SKINS.md",
        "GESTURES.md"
    ]
    for doc_name in docs_to_mirror:
        src = XENNEX_DOCS_ROOT / doc_name
        if src.exists():
            dest = vault_folder / doc_name
            shutil.copy2(src, dest)
            synced_files.append(str(dest))

    return {
        "success": True,
        "vault_path": str(vault_path),
        "folder": str(vault_folder),
        "synced_files_count": len(synced_files),
        "synced_files": synced_files
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Xennex documentation to Obsidian Vault")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT_PATH), help="Path to Obsidian Vault")
    args = parser.parse_args()

    result = sync_vault(Path(args.vault).expanduser())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
