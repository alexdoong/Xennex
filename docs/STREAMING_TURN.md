# Conexão alternativa opcional — Cloudflare TURN

## Publicação em produção (01/11/2026)

Worker e assets publicados via Wrangler4.156.1 em
https://xennex-live.alexdoong11.workers.dev, versão
`b7dad075-8858-4d5a-9b95-49eb00353e4a`. **TURN continua desligado**:
POST `/api/turn-credentials` responde503/turn_disabled; não foram criados secrets
ou emitidas credenciais reais. A publicação não comprova resolver a conexão do
amigo e não substitui o teste de relay condicionado ao controle de gastos.

HTML/JS/CSS e protocolo conferidos; sala de teste Edge com três transmissores,
áudio e migração passou no endereço publicado. Nenhuma sala existente foi
alterada. Versão anterior para reversão:`4200db0c-350d-4282-85e3-57042cde8538`;
histórico remoto salvo localmente em bin/. Login oficial por dispositivo e
permissão específica workers_scripts:write autorizados pelo usuário; instruções
reproduzíveis em cloudflare_pages/README.md.

## Estado da entrega (31/10/2026)

Implementação local pronta para configurar e testar com serviço real. Não houve
deploy, criação de chave, uso de TURN real ou ativação de cobrança. P2P permanece
o padrão. A captura e o transporte de áudio existentes não foram substituídos.

Após uma falha de entrada, **Tentar conexão alternativa** abre um campo para o
código privado fornecido pelo dono da sala. **Conectar com alternativa** solicita
credenciais e cria uma nova tentativa somente desse participante, com conexão
direta e retransmissão disponíveis. Abrir o painel não solicita credenciais.
Cancelar ou falhar a solicitação não reinicia a sala. O modo não fica salvo.

O acesso e as credenciais ficam na memória da aba. O código não é chave da API da
Cloudflare e não deve ser colocado no convite público, bundle, Git ou query string.
Quando conectado, o participante vê a validade e pode **Renovar acesso**. A renovação
atualiza configurações ICE dessa instância e conexões próprias sem iniciar renegociação,
fechar vídeos ou mudar os demais participantes. Se alguma atualização falhar, a UI
informa que não confirmou a renovação. P2P/alternativa são modos de configuração;
o caminho efetivamente escolhido aparece nas estatísticas de Qualidade.

Por padrão a credencial dura 12 horas. Renove antes de vencer se a sessão for mais
longa: Cloudflare pode encerrar alocações com credencial vencida. A aplicação não
renova nem solicita serviço automaticamente. O administrador pode configurar de
600 a 43200 segundos. [Documentação de credenciais](https://developers.cloudflare.com/realtime/turn/generate-credentials/)
e [expiração de alocações](https://developers.cloudflare.com/realtime/turn/faq/).

Para voltar ao padrão, sair e entrar normalmente descarta as credenciais. A tentativa
alternativa não está disponível durante uma sessão ativa para evitar parar fontes
existentes. Recuperação seletiva de uma mídia já conectada é um incremento separado.

## Componentes e contrato

- `frontend/src/features/stream/turnFallback.ts`: valida endpoint, prazo e servidores;
  POST explícito cancelável, sem cookies/cache/redirecionamentos; timeout de 10 s.
- `TurnFallbackPanel.tsx`: consentimento local, código em memória, cancelamento,
  renovação manual e descarte de respostas de outra geração de sessão.
- `RoomClient.start(..., lease?)`: aceita alternativa antes da entrada; o caminho
  sem lease conserva a configuração anterior. `renewTurn` não chama start/leave.
  PeerJS recebe uma configuração isolada por instância, sem mutação do padrão global.
- `cloudflare_pages/worker.mjs`: POST `/api/turn-credentials`; Worker chama a API da
  Cloudflare com segredo servidor, valida resposta e retorna somente iceServers e
  expiresAt (milissegundos Unix). Não recebe URLs de destino ou TTL do cliente.
- `cloudflare_pages/wrangler.jsonc`: mantém os assets em dist e chama código apenas
  para `/api/*`. `TURN_ENABLED=false` por padrão. A hospedagem estática continua
  disponível sem secrets, binding de rate limit ou acesso à API TURN.

O broker exige código de acesso com pelo menos 24 caracteres, binding de rate limit
e origem permitida. Faz comparação de hashes e limita solicitações por IP (10/minuto
por localidade, conforme o binding). Não é autenticação de contas nem teto financeiro.
O corpo não aceita configurações arbitrárias; upstream é fixo em rtc.live.cloudflare.com.
Não loga código, token de API, credenciais, IPs ou SDP. Respostas e erros não são cacheados.
CORS aceita origem do Worker e a lista explícita TURN_ALLOWED_ORIGINS, sem wildcard.

## Preparação na Cloudflare

**Não habilitar antes de verificar o controle de gastos da conta.** A franquia
mensal de 1000 GB é compartilhada entre SFU e TURN, com cobrança acima dela;
Workers possuem limites próprios. TTL, rate limit, botão opcional e alertas não
garantem custo zero. A documentação consultada não comprova um bloqueio financeiro
automático para esta conta. [Preços oficiais](https://developers.cloudflare.com/realtime/sfu/platform/pricing/).

1. Compilar: `npm run build:web` em frontend. O bundle está em cloudflare_pages/dist.
2. No painel Cloudflare Realtime TURN, criar a chave apropriada. Não enviar tokens
   pelo chat. Guardar os três valores como secrets do Worker usando Wrangler já
   disponível/autenticado na conta correta:

   ```powershell
   wrangler secret put TURN_KEY_ID --config cloudflare_pages/wrangler.jsonc
   wrangler secret put TURN_KEY_API_TOKEN --config cloudflare_pages/wrangler.jsonc
   wrangler secret put TURN_ACCESS_CODE --config cloudflare_pages/wrangler.jsonc
   ```

   TURN_ACCESS_CODE é um código aleatório próprio para os amigos autorizados,
   preferencialmente 32 bytes aleatórios codificados em base64url. Os outros dois
   valores são da Cloudflare e nunca chegam ao frontend. Não criar .dev.vars com
   dados reais em artefatos distribuídos; esses arquivos e .wrangler são ignorados.
3. Revisar name, conta e origens no wrangler.jsonc. Origem do próprio Worker é aceita;
   `https://appassets` permite o app. Outro domínio web precisa de autorização explícita.
   Um preview separado pode usar `--name xennex-live-preview`; não substituir a
   hospedagem atual sem conferir os assets e guardar a configuração anterior.
4. Publicar primeiro com TURN_ENABLED=false. Confirmar site, sala normal e POST
   com retorno 503 sem emissão de credenciais. O deploy precisa incluir Worker e
   assets; enviar apenas dist em Pages/Static Assets não instala o broker.
5. Após resolver a restrição de gastos e aprovar a ativação real, mudar TURN_ENABLED
   para true e publicar o Worker. Conferir binding TURN_RATE_LIMITER obrigatório.
6. O web usa `/api/turn-credentials` na mesma origem. O app usa o endereço público
   salvo nas opções. Para um broker separado, definir VITE_TURN_ENDPOINT HTTPS e
   recompilar ambos. Não colocar código de acesso ou chave privada em variáveis Vite.
7. Testar um participante com alternativa e outros em P2P, confirmando o caminho
   relay nas estatísticas. O ensaio local feito nesta entrega usa relay sintético
   indisponível e conexão direta real: ele não valida o relay da Cloudflare.

## Desativação e limites

Publicar TURN_ENABLED=false interrompe novas emissões. Credenciais já emitidas
podem continuar válidas até o vencimento; para encerrar esse acesso imediatamente,
usar a revogação oferecida pela Cloudflare. Isso não encerra as conexões P2P.
Remover o painel/broker não exige migrar o protocolo de sala.

TURN é alternativa de conectividade, não garantia de FPS e não substitui SFU.
Mantemos WebRTC: captura por programa vem do serviço nativo de áudio Windows.
Um site não ganha acesso a áudio de processos ao trocar o protocolo de transporte;
captura de aba/janela depende das APIs e permissões do navegador. Nesta entrega
não há ponte nativa aberta a sites externos nem nova captura de áudio.

## Verificação

`npm test` inclui validação de leases, origem/auth/rate limit, TTL fixo no servidor,
segredos protegidos, defaults sem serviço externo, isolamento de participantes,
renovação sem restart e retorno ao padrão. O teste de migração aguarda mídia de
forma assíncrona, preservando a expectativa anterior de receber a mesma fonte.

`tests/browser-streaming.mjs` cobre broker desligado, nenhuma consulta no caminho
normal/abertura do painel, tentativa alternativa e renovação com resposta sintética,
sem persistir acesso ou interromper vídeos dos outros, além das regressões existentes.
Um teste de relay real e implantação com Wrangler continuam necessários antes de
declarar conectividade resolvida para o amigo.
