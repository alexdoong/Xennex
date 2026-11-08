# Revisão de segurança e automação

Revisão iniciada em 21/09/2026, sobre a árvore de desenvolvimento 0.2.3.
Não é certificação de segurança nem auditoria exaustiva de todas as funcionalidades.

## Avaliação das observações recebidas

| Observação | Verificação e tratamento |
| --- | --- |
| Nenhum CI | Confirmado. Adicionado `.github/workflows/ci.yml`, com permissões somente de leitura, builds React/web/.NET e testes em Windows. Passa a executar no GitHub depois do commit/push. |
| RoomClient/RoomCoordinator sem testes | Incorreto no estado atual. `frontend/tests/streaming.test.mjs` cobre presença, eleições, falhas, reconexão, assinaturas, limites e limpeza sem abrir o app; há também integração WebRTC real. Scripts de teste são testes automatizados mesmo sem framework adicional. |
| Leitura fora de wwwroot | Confirmada a construção insegura do caminho, reproduzida com arquivo privado sintético e caminho absoluto de drive. A explicação original sobre AbsolutePath decodificar todos os separadores percentuais não corresponde ao comportamento observado. A correção valida RawUrl, normaliza o caminho, restringe ao diretório público e recusa reparse points. |
| CORS aberto | Removido o wildcard; origens externas recebem 403. Isso é separado da autorização de WebSockets. |
| Captura de áudio/vídeo acessível por WebSocket | Achado adicional: endpoints não autenticavam o cliente. Agora exigem origem exata do app e token aleatório de 256 bits por execução; o token só chega ao frontend pela ponte nativa. |
| Ponte nativa exposta após navegação | Achado adicional: a navegação da WebView privilegiada não estava explicitamente restrita. Agora somente o documento index.html do app pode ocupar a janela; frames são bloqueados, mensagens têm origem validada e novas janelas HTTP(S) iniciadas pelo usuário abrem no navegador externo. |
| Atualizador aceita URL arbitrária | Confirmado e corrigido. Reconsulta a release oficial, exige ZIP portátil de nome exato/versão estável mais recente, SHA-256 da API e tamanho esperado; restringe redirecionamentos ao GitHub/CDN. Não executa EXE/MSI recebido do frontend. |
| ZIP/assinatura sem verificação | Instalador repete SHA-256, rejeita caminhos perigosos, duplicatas, symlinks e tamanho excessivo; confere integridade Authenticode e fingerprint esperado dos três executáveis próprios. O app aguarda a confirmação da validação antes de encerrar. |
| Certificado gerado automaticamente no empacotamento | Removido. O empacotador exige a chave cujo fingerprint público está em assets/publisher-thumbprint.txt. Ausência da chave falha explicitamente. |
| “Antivírus aceita qualquer malware assinado” | Exagero. Confiar na chave amplia a confiança no publicador, mas assinatura não substitui análise antimalware/reputação. README e instalador agora explicam a confiança adicional e o caráter autoassinado. |
| Logs fragmentados, áudio síncrono e callbacks globais | Confirmados como dívida técnica; detalhes e próximos passos abaixo. |
| “Meses sem commit” e “basicamente v0.3” | Há uma árvore grande sem commit; não se pode inferir duração ou versão nova pelo tamanho. A versão oficial continua a definida no csproj. A revisão não criou commits nem alterou a versão. |

## Fronteiras e limites

O token impede páginas comuns de ler a captura local. Não pretende isolar processos
maliciosos já executando com a mesma conta do Windows: eles podem inspecionar
processos/arquivos. Conteúdo JavaScript empacotado com o app continua confiável.
A política de navegação não substitui escaping/validação de cada entrada do frontend.

A atualização confia nos metadados HTTPS da release do repositório configurado.
O hash autentica o arquivo em relação a esses metadados; não é uma assinatura
independente do ZIP. A assinatura dos EXEs não cobre por si só JS, CSS e scripts.
Comprometimento da conta GitHub ou da máquina de publicação continua relevante;
proteger essas contas/chaves e eventualmente assinar um manifesto completo são
trabalhos distintos. Releases antigas sem digest são recusadas pelo atualizador;
a instalação manual continua possível. Não existe fallback inseguro.

O certificado atual não foi rotacionado, exportado como chave privada nem removido
dos computadores. O novo atualizador verifica a chave fixada sem exigir que ela
seja adicionada a Root. O instalador de confiança permanece opcional e explícito,
para manter compatibilidade com o pacote. Trocar a chave exige um plano de migração.

## Testes e execução

- `npm test` em frontend: salas, qualidade, captura, cancelamento e seleção.
- `powershell -File scripts/tests/test_ci.ps1`: testes de segurança, skins, jogos,
  IA local, Gestures, empacotamento e atualização. Sem câmera/modelos/chave privada.
- `SecurityTests`: 39 verificações, incluindo servidor HTTP real, requisições
  brutas, WebSockets autorizados/negados, origem da UI, URLs e hash/tamanho.
- `test_update_security.ps1`: ZIP válido, caminhos maliciosos, duplicatas, hash
  errado/ausente e executável sem assinatura; nunca instala uma atualização real.
- `test_stream_native.ps1`: instância limpa do app, três ciclos de captura da
  própria janela, rejeição de token incorreto e bloqueio de navegação externa.
  É teste interativo de Windows separado do CI e exige Playwright.
- `test_release.ps1`: integridade dos bundles, dados sanitizados e preservação de
  configuração/skins em duas atualizações.

Resultado da rodada: builds app/web/.NET passaram; a bateria de CI local passou,
incluindo 39 verificações de segurança, 23 de skins, 104 de IA, 23 do supervisor
Gestures e 21 testes Python, além de jogos, salas e empacotamento/atualização.
No pacote self-contained, três capturas nativas iniciaram em 896/209/205 ms; token
de vídeo inválido foi recusado e navegação externa da WebView foi bloqueada.
O instalador também aceitou as assinaturas reais do pacote com a chave fixada.
O executável principal e o CaptureWorker da raiz correspondem ao pacote assinado.

A execução local dos comandos não equivale a uma execução já concluída no GitHub.
Publicação e assinatura de releases ficam fora do CI: não há segredos, deploy,
certificado privado nem downloads de modelos no workflow.

## Pendências ordenadas

1. Consolidar e revisar os commits existentes por funcionalidade, com todos os
   arquivos de suporte/testes. Não commitar binários, Data pessoal ou chaves.
   Um ZIP de backup ajuda, mas não substitui histórico Git e cópia externa.
2. Tornar assíncrono o início do áudio sem criar corrida entre início, cancelamento,
   troca de dono da captura e fechamento de janela. WaitOne(4000) continua no
   serviço atual; deslocar apenas uma chamada para Task.Run não resolve o ciclo todo.
3. Unificar logs dos serviços em AppLog com rotação e níveis, distinguindo
   cancelamento normal de erros que merecem registro.
4. Substituir gradualmente callbacks globais por mensagens tipadas. As chamadas
   ExecuteScriptAsync observadas usam booleanos/comandos fixos; a presença da
   interpolação, sozinha, não demonstrou injeção de JavaScript.
5. Atualização transacional com rollback após falha de cópia/energia, manifesto
   assinado cobrindo todos os assets e política explícita de rotação de chave.
6. Evoluir cobertura de integração por módulo sem baixar modelos nem usar
   hardware pessoal no CI. Testes reais entre redes diferentes continuam manuais.

Referências: [digests de assets no GitHub](https://docs.github.com/en/rest/releases/assets)
embasam a verificação SHA-256; [Authenticode](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/authenticode)
explica integridade/publicador; [SmartScreen](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)
explica a verificação de reputação, distinta da assinatura.
