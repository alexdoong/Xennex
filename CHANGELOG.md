# Histórico de mudanças

## 0.2.4 (08/11/2026)

Consolida o trabalho desde `a57d925` (12/09/2026, versão 0.2.3), alinhando o
aplicativo Windows, o site público (`xennex-room-v3`) e o aplicativo Android de
transmissão de tela na versão `0.2.4`.

### Funcionalidades

- **Biblioteca de artes e VR:** catálogo SQLite para pastas locais, Galeria e
  Explorador, busca/filtros salvos, tags, favoritos, coleções, miniaturas,
  metadados de PNG/ComfyUI, comparação, geração local via ComfyUI e visualizador
  em VR (SteamVR/OpenVR). Inclui seleção/edição de até 100 itens, operações de
  arquivo com prévia e confirmação, destinos visuais, dois painéis e busca rápida
  no catálogo. [Uso e limites](docs/ASSET_LIBRARY.md) e [VR](docs/VR.md).
- **Jogos:** a antiga aba demonstrativa de WuWa deu lugar a uma biblioteca de
  jogos e sessões com definições editáveis, métricas, histórico, comparação e
  espaço visual para personagens, habilidades e planos.
  [Arquitetura](docs/GAME_ANALYTICS.md).
- **IA local e Alice:** conversas persistentes, fila com orçamento de RAM/VRAM,
  integração opcional com Ollama local e API compatível, salas com especialistas,
  planos, cadernos e avaliação de execuções, além do núcleo de memória contínua
  e multimodal da Alice. Nenhum modelo é baixado automaticamente.
  [Uso](docs/LOCAL_AI.md) e [salas](docs/LOCAL_AI_ROOMS.md).
- **Gestos:** controle do PC por câmera com modo de teste inicial, perfis e
  gravação de poses/movimentos; worker Python modular e supervisão nativa.
  [Uso e limites](docs/GESTURES.md).
- **Interface e skins:** painel compacto com posições/recolhimento, estado
  compartilhado com a janela cheia e animação por quadros de renderização.
  O editor de skins ganhou prévia, histórico, presets, Liquid Glass, estrutura da
  janela, cartões ajustáveis e reordenação/colunas dos blocos de Configurações.
  [Painel](docs/COMPACT_MODE.md) e [skins](docs/SKINS.md).
- **Transmissão (Windows, Web e Android):** salas P2P (`xennex-room-v3`) com
  múltiplas fontes e assinaturas independentes, captura nativa de janela/monitor
  (WGC e DXGI para fullscreen), captura experimental de jogos OpenGL, redução GPU
  antes do readback, áudio por processo, aviso visual silencioso de nova tela,
  negociação de codecs por capacidade, chat/notas/tarefas colaborativas na sala
  e APK nativo para Android (`MediaProjection` + `libwebrtc`).
  [Streaming](docs/STREAMING.md) e [Android](docs/ANDROID_STREAMING.md).

### Plataforma, segurança e manutenção

- Ícone corrigido nas janelas e na bandeja; abrir o app novamente sinaliza a
  instância existente para restaurar sua janela.
- Atualização endurecida com validação de origem, versão, hash, ZIP e assinatura;
  dados em `Data/` e skins pessoais são preservados. Revisão e limites em
  [segurança](docs/SECURITY_REVIEW.md).
- Versão do projeto alterada para 0.2.4. Build web, app e CaptureWorker têm
  rotas separadas; `wwwroot/`, `cloudflare_pages/dist/`, `bin/`, `Data/`, caches,
  modelos pessoais e certificados privados continuam fora do Git.
- CI e testes determinísticos para segurança, Biblioteca, Jogos, IA local,
  Gestos, skins, painel compacto, streaming e empacotamento. Auxiliares em
  `scripts/` para ComfyUI, telemetria, inspeção e Obsidian são opcionais; não
  representam integração automática dessas ferramentas na interface.

### Verificação desta consolidação

- `scripts/run_dev.ps1 -BuildOnly`: frontend, app e CaptureWorker compilados.
- `npm run build:web`, `npm test`, `npm run lint` e `scripts/tests/test_ci.ps1`:
  concluídos. O lint ainda emite avisos sem erro.
- Testes Playwright de Biblioteca, painel compacto/skins, Jogos e Gestos:
  concluídos. Captura real, câmera, áudio, bandeja e instalação em outro PC
  ainda precisam do roteiro manual em [TESTING.md](docs/TESTING.md).
