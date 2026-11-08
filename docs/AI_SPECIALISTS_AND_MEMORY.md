# Escritório de Especialistas e Arquitetura de Memória — Xennex

Registrado em 26/09/2026; revisado em 27/09/2026. Documento de visão para a expansão do sistema multi-agente local do Xennex.

Status: chats, especialistas, salas, fila e propostas de caderno já possuem implementação.
Busca web/MCP, ferramentas executáveis e treinamento continuam planejados.
Notas aprovadas entram no contexto; isso não treina nem altera os pesos do modelo.
Os scripts auxiliares adicionados em scripts/ não comprovam integração com a aba.
LOCAL_AI.md, LOCAL_AI_ROOMS.md e o código são as referências do comportamento atual.

---

## 1. Visão do Ecossistema: O "Discord" de Modelos e Especialistas

O objetivo é transformar a aba de IA do Xennex em um ambiente dinâmico de ideação, estudo e desenvolvimento assistido, onde diferentes mentes artificiais trabalham em conjunto com o usuário:

- **Painel de Especialistas (Estilo Roster do Discord)**:
  - Uma barra lateral visual listando todos os modelos e personas criados e disponíveis (ex: especialistas em arquitetura, segurança, frontend, som, novidades tecnológicas, etc.).
  - Indicação clara de quais modelos estão instalados localmente (Qwen 2.5-Coder, LLaMA 3, Ternary Bonsai, DeepSeek, etc.) ou se algum serviço externo está habilitado.
- **Chats como Projetos Vivos**:
  - Toda conversa é tratada como um projeto ou espaço de trabalho contínuo, mesmo que seja apenas uma discussão conceitual ou estudo.
  - O usuário pode adicionar ou convocar especialistas dinamicamente para o chat (ex: convidar o especialista em segurança para avaliar um trecho de código discutido).

---

## 2. Arquitetura de Memória Híbrida: Caderno Markdown vs. KV Cache

Modelos locais sofrem degradação de raciocínio (*prompt drift*) e estouram a VRAM se o histórico bruto de dezenas de milhares de tokens for mantido permanentemente na janela de contexto. A proposta distingue contexto temporário e notas persistentes. KV cache é um cache de atenção administrado pelo motor, não um diário nem memória garantida entre reinícios. O aplicativo persiste histórico e notas e monta o contexto enviado ao modelo:

```
┌────────────────────────────────────────────────────────┐
│           CAMADA 1: KV CACHE (CURTO PRAZO)             │
│  - Memória volátil e veloz mantida pelo motor local    │
│  - Continuidade imediata dos turnos da conversa        │
│  - Permite raciocínio rápido no diálogo do dia         │
└───────────────────────────┬────────────────────────────┘
                            │ Síntese e Extração
                            ▼
┌────────────────────────────────────────────────────────┐
│      CAMADA 2: CADERNO DE NOTAS EM MARKDOWN            │
│                 (LONGO PRAZO VIVO)                     │
│  - Cada especialista mantém seu próprio caderno .md    │
│  - Interpretação própria sob a ótica da especialidade │
│  - Revisão interativa com o usuário                    │
│  - Aprendizado progressivo do estilo e preferências    │
└────────────────────────────────────────────────────────┘
```

### A. Interpretação Própria por Especialidade
- Em vez de um resumo genérico único, cada especialista extrai e anota o que é relevante para o seu domínio:
  - O **Especialista em Segurança** anota contratos, portas abertas, riscos e requisitos de autenticação.
  - O **Especialista em Frontend** anota tokens de design, ergonomia, responsividade e componentes reutilizáveis.
  - O **Especialista em Arquitetura** anota fluxo de dados, separação de camadas e dependências.

### B. Revisão Colaborativa com o Usuário ("Lembrar disso ou não?")
- As notas são persistidas na biblioteca JSON de Data/ai e podem ser exportadas em Markdown. A visão de um caderno .md sincronizado e editável externamente ainda exige implementação específica.
- Após rodadas de conversa ou marcos importantes, o especialista pode propor itens para sua memória de longo prazo e perguntar:
  > *"Identifiquei este padrão de trabalho e esta decisão. Faz sentido eu anotar no meu caderno para lembrar nos próximos dias?"*
- O usuário valida, corrige ou rejeita, mantendo controle total sobre o que a IA aprende.

### C. Evolução de Afinidade e Estilo
- Conforme as notas são confirmadas ao longo do tempo, o especialista passa a entender a forma como o usuário prefere organizar projetos, nomenclaturas favoritas e regras específicas.
- O especialista passa a se comunicar de forma mais personalizada e direta, reduzindo atritos em sessões futuras.

---

## 3. Sistema de Skills (Ferramentas) para Especialistas Locais

Para que os modelos locais tenham autonomia real e resolvam problemas no computador:

1. **Pesquisa na Web (Web Search via Tool Calling / MCP)**:
   - Especialistas (como o Qwen 2.5-Coder) recebem a ferramenta de busca para puxar documentações recentes, APIs atualizadas e soluções de bugs em fóruns.
   - O harness intercepta a chamada de ferramenta, executa a pesquisa e devolve os dados limpos para o modelo sintetizar.
2. **Especialista em Novidades e Atualidades**:
   - Um agente focado em rastrear novidades do ecossistema de IA (lançamentos de modelos abertos, papers, bibliotecas open-source) e sugerir melhorias para o Xennex.
3. **Leitura e Auditoria de Código**:
   - Ferramentas com permissão de leitura cirúrgica de arquivos do projeto para contextualizar respostas sem carregar a pasta inteira na memória.

---

## 4. Integração com a Fila Central de Recursos

- Todos os especialistas operam sob a autoridade da **Fila Central de Recursos** (`LocalAiService`).
- O serviço admite trabalhos um por vez com orçamento padrão de 75% (margem de 25%), estimativas e pausa por pressão. Não há reserva física de RAM/VRAM nem garantia contra travamentos: outros programas podem consumir recursos depois da admissão. A política pode aguardar recursos, portanto não prometer FIFO estrito em todos os casos.

---

## 5. Dinâmica de Salas e Reuniões Multi-Especialista

- A colaboração entre especialistas ocorre através do sistema de **Salas** (`src/Services/LocalAi/LocalAiRooms.cs` e [LOCAL_AI_ROOMS.md](LOCAL_AI_ROOMS.md)).
- **Ordem de Fala e Protocolo**: O usuário ou o plano da reunião define a ordem em que os especialistas são acionados.
- **Contexto Isolado com Síntese Compartilhada**:
  - Cada especialista entra na conversa conhecendo o papel dos colegas, mas lê estritamente seu próprio caderno revisado.
  - O contexto seleciona mensagens anteriores em ordem cronológica, com autoria e limites de tamanho; cortes são identificados. Isso não implica resumo semântico automático de todo o histórico.
- **Auditoria e Checkpoints**:
  - Trabalhos e estado da biblioteca possuem persistência/checkpoints. Métricas de tokens dependem do motor e podem não estar disponíveis; fontes registradas de contexto não comprovam consulta à web.
  - Se um especialista falhar ou for cancelado, a reunião é interrompida de forma segura sem corromper o estado do projeto.
