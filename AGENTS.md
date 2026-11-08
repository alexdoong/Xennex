# Manual Geral de Agentes de IA — Xennex (Master Agent Guide)

Bem-vindo ao repositório do **Xennex**. Este documento serve como índice mestre, roteador de contexto e protocolo de operação para agentes autônomos de IA (modelos locais como Qwen/DeepSeek/Codestral e modelos avançados em nuvem como Gemini/Astra).

---

## 1. Arquitetura de Operação: Gerente vs. Especialista

Adotamos formalmente o modelo de engenharia colaborativa em dois níveis (**Dual-Tier Agentic Architecture**):

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       IA GERENTE / ARQUITETO                            │
│                 (Gemini Pro / Astra 6 / GPT-4o)                         │
│  - Raciocínio sistêmico profundo e visão macro do projeto               │
│  - Decomposição de features em tarefas cirúrgicas e contratos de API    │
│  - Auditoria de segurança, code review de diffs e validação de regras   │
│  - Gatekeeper final de qualidade contra a suíte de testes (CI)          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Demanda Cirúrgica + Contrato Estrito
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     IA ESPECIALISTA / EXECUTOR                          │
│               (Qwen 2.5-Coder 14B/32B / Dev Local / MCP)                │
│  - Implementação veloz de código, funções, telas e testes unitários     │
│  - Execução local sem cobrança de API; desempenho depende do hardware             │
│  - Consultas externas na web via Tool Calling / MCP quando necessário   │
│  - Execução focada com escopo estrito em arquivos delimitados           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Estratégia de colaboração e seus limites

O usuário levantou a dúvida: *"no futuro to querendo usar vcs mais como um gerente ou coisa do tipo sabe? Mais para realizar a verificação do que foi realizado, mas não sei se seria a melhor opção"*.

A separação entre planejamento, execução e revisão é a estratégia desejada para este projeto. Ela pode ajudar a distribuir trabalho e custos, mas não garante qualidade superior nem exige usar mais de um agente em toda tarefa:

1. **Eficiência de Custo e Recursos**: Modelos de nuvem de ponta cobram por token e possuem limites de cota. Gastar tokens caros para escrever código repetitivo (boilerplates, mapeamento de propriedades, preenchimento de testes) é ineficiente. A execução local dispensa cobrança por chamada de API, mas consome energia, memória e tempo de processamento.
2. **Controle de Contexto**: Tarefas delimitadas e regras modulares (`.agents/rules/`) reduzem contexto desnecessário. A qualidade depende do modelo, da quantização e da tarefa; dividir trabalho não elimina erros ou perda de contexto.
3. **Privacidade e Segurança**: O código proprietário, chaves locais, tokens de sessão e dados de teste em `Data/` devem permanecer na máquina durante execuções locais. Ferramentas de busca, conectores ou revisão em nuvem podem transmitir entradas; não enviar segredos ou dados pessoais.
4. **Visão Holística e Gatekeeping**: Modelos como Gemini/Astra possuem raciocínio arquitetural avançado, identificando efeitos colaterais em cadeia, falhas sutis de concorrência ou riscos de segurança que modelos menores deixam passar. A revisão também pode falhar: confirmar conclusões com código, testes e evidências, sem tratar nenhum modelo como infalível.

---

## 2. Taxonomia Estrutural do Repositório (Onde Cada Coisa Mora)

Para manter o repositório organizado e evitar proliferação de pastas arbitrárias, toda adição de código deve respeitar a estrutura existente:

```
Xennex/
├── AGENTS.md                  # Master Guide e Roteador de Contexto para Agentes
├── Xennex.sln / .csproj       # Solução e projeto principal .NET 8 WPF
├── .agents/
│   └── rules/                 # Regras modulares com frontmatter para harnesses
├── src/                       # Código C# do Backend e Integração com Windows
│   ├── Program.cs             # Ponto de entrada, Single Instance e unhandled exceptions
│   ├── UI/                    # Janelas WPF, WebView2 e ciclo de vida visual
│   ├── Interop/               # ApiBridge.cs (ponte COM declarativa com o frontend)
│   ├── Models/                # Modelos de dados e contratos de transferência
│   ├── Services/              # Lógica de negócio e serviços de domínio
│   │   ├── LocalAi/           # Orquestração de IA local, fila, memória e salas
│   │   ├── GameAnalytics/     # Análise de jogos, biblioteca, esquemas e eventos
│   │   ├── Gestures/          # Supervisão e comunicação com o worker de gestos
│   │   ├── Security/          # Sanitização, validação de tokens e restrição de loopback
│   │   └── Updates/           # Política de atualização e verificação Authenticode
│   ├── CaptureWorker/         # Executável auxiliar isolado para Windows Graphics Capture
│   └── Android/               # Aplicativo Android nativo de transmissão de tela (MediaProjection + WebRTC)
├── frontend/                  # Interface do Usuário (React + TypeScript + Vite)
│   ├── src/layout/            # Moldura da janela, topbar e painel compacto
│   ├── src/features/          # Módulos independentes por funcionalidade (stream, ai, games...)
│   ├── src/components/        # Componentes visuais compartilhados
│   ├── src/hooks/             # Hooks de ciclo de vida e estado sincronizado
│   ├── src/styles/            # CSS modular por área (importados ordenadamente em index.css)
│   └── src/webview.d.ts       # Contratos de tipagem estrita da ponte nativa
├── scripts/                   # Automação de engenharia, empacotamento e testes
│   ├── package_release.ps1    # Script oficial de empacotamento e assinatura
│   ├── build_android.ps1      # Script de compilação, testes e lint do APK Android
│   ├── hand_motion.py         # Script Python de rastreamento de mãos via MediaPipe
│   └── tests/                 # Suíte determinística de testes (test_ci.ps1)
├── docs/                      # Especificações arquiteturais e manuais de domínio
├── Data/                      # Dados privados do usuário (ignorado no Git, preservado em updates)
├── wwwroot/                   # Bundle de distribuição web gerado pelo Vite (nunca editar à mão)
└── assets/                    # Assets estáticos padrão, certificados e modelos públicos
```

---

## 3. Roteador de Contexto (Onde Consultar Antes de Modificar)

Para evitar sobrecarga de contexto, **NUNCA** carregue toda a documentação de uma vez. Consulte a tabela abaixo para saber exatamente qual arquivo ler dependendo do que for alterar:

| O que você vai fazer? | Arquivo de Documentação Obrigatório |
| :--- | :--- |
| **Padrões de código, Clean Code e convenções** | `.agents/rules/coding-standards.md` e `docs/CODING_RULES.md` |
| **Limites de segurança, tokens, portas e sanitização** | `.agents/rules/security-and-safety.md` e `docs/SECURITY_REVIEW.md` |
| **Garantia de qualidade, execução de CI e testes** | `.agents/rules/testing-and-verification.md` e `docs/TESTING.md` |
| **Empacotamento, distribuição ou atualização do app** | `.agents/rules/release-packaging.md` |
| **Painel compacto, recolhimento direcional ou docking** | `docs/COMPACT_MODE.md` |
| **Transmissão, captura WGC, áudio ou WebRTC** | `docs/STREAMING.md` |
| **Transmissão de tela no Android (APK MediaProjection + WebRTC)** | `docs/ANDROID_STREAMING.md` e `docs/STREAMING.md` |
| **IA local, especialistas, cadernos e memória** | `docs/LOCAL_AI.md`, `docs/LOCAL_AI_PLAN.md`, `docs/LOCAL_AI_ROOMS.md` e `docs/AI_SPECIALISTS_AND_MEMORY.md` |
| **Modelos de IA suportados, pesos e orçamentos** | `docs/LOCAL_AI_MODELS.md` |
| **Rastreamento de gestos por visão computacional** | `docs/GESTURES.md` |
| **Sistema de skins, cores e personalização visual** | `docs/SKINS.md` |
| **Biblioteca de artes, galeria e explorador** | `docs/ASSET_LIBRARY.md`, `docs/ASSET_LIBRARY_PLAN.md` e `docs/ASSET_LIBRARY_REFERENCES.md` |
| **Biblioteca no VR, SteamVR/OpenVR ou Rift S** | `docs/VR.md` e `docs/ASSET_LIBRARY.md` |
| **Métricas e biblioteca de jogos** | `docs/GAME_ANALYTICS.md` |
| **Integração futura de calendário e hub de vida** | `docs/FUTURE_LIFE_HUB.md` |

---

## 4. Protocolo de Progresso Contínuo: Como Geramos e Anotamos Informações

Para que o projeto evolua de maneira contínua, sem perda de contexto entre sessões ou trocas de modelo de IA, seguimos o ciclo de 4 etapas:

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ 1. PLANEJAMENTO │ ───>  │  2. EXECUÇÃO    │ ───>  │  3. VALIDAÇÃO   │ ───>  │  4. REGISTRO    │
│  (IA Gerente)   │       │  (Especialista) │       │   (CI / Testes) │       │   (Docs / Mem)  │
└─────────────────┘       └─────────────────┘       └─────────────────┘       └─────────────────┘
```

1. **Planejamento & Contratos (IA Gerente)**:
   - Define a arquitetura da nova funcionalidade.
   - Especifica assinaturas de métodos, modelos de dados e restrições.
   - Atualiza ou cria a especificação correspondente em `docs/`.
2. **Execução Cirúrgica (Especialista Local)**:
   - Recebe apenas as regras relevantes de `.agents/rules/` e o contrato estrito.
   - Implementa o código mantendo o estilo plano (*guard clauses*).
   - Utiliza Tool Calling (pesquisa web / leitura de arquivo) para dirimir dúvidas pontuais de bibliotecas.
3. **Validação Obrigatória (Verification Gate)**:
   - Executa `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_ci.ps1`.
   - Se houver falha, o código é ajustado imediatamente antes de qualquer entrega.
4. **Registro de Progresso & Memória Contínua**:
   - **Histórico do Projeto**: Registre o incremento em `docs/AGENT_CONTEXT.md` com data, escopo implementado e decisões técnicas.
   - **Cadernos dos Especialistas**: Para os agentes locais na aba de IA, decisões e preferências aprendidas são propostas para o caderno Markdown correspondente sob aprovação do usuário (*"Lembrar disso ou não?"*), conforme especificado em `docs/AI_SPECIALISTS_AND_MEMORY.md`.
