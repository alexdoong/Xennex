# Salas de IA local

## Começar

1. Configure o motor em **IA local → Conexão e orçamento**.
2. Abra **Especialistas** e cadastre nome, papel, instruções e, se quiser, um modelo
   próprio. Modelo vazio usa o modelo global. Perfis são instruções e identidade,
   não modelos treinados ou certificações de competência.
3. Crie uma **Nova sala de projeto** ou transforme uma conversa existente.
4. Em **Editar plano e membros**, defina objetivo, plano em Markdown e participantes.
   Cada membro possui permissões para receber plano, histórico e próprio caderno.
5. Na próxima rodada, selecione um especialista ou a equipe, escreva a pergunta
   e escolha de uma a três rodadas. A ordem segue os selecionados; respostas
   anteriores entram no contexto dos próximos membros quando autorizadas.

Presença na sala não significa carregar o modelo. A mesma fila serial controla
conversas comuns e especialistas, com margem de memória padrão de 25%. Cada
resposta mostra autor, papel, modelo e um relatório do contexto utilizado.
Especialistas recebem os nomes e papéis dos colegas da sala e podem pedir ajuda
por texto. Convidar alguém ou iniciar uma nova rodada continua sendo uma ação sua.

## Plano e memória

O plano mantém até 50 revisões. Planos, membros e permissões só mudam quando a
sala não possui trabalho pendente. Perfis aguardam a fila global terminar.
Edições usam revisão otimista: um formulário antigo não substitui silenciosamente
uma versão mais nova.

Cada especialista tem um caderno por projeto, com notas em Markdown. Estados:
proposta, hipótese, confirmada por você e superada. **Propor memória** executa uma
chamada explícita para produzir uma proposta, registra origem/data e referências
às mensagens usadas; não transforma o resultado em fato. Só hipóteses e notas
confirmadas podem ser recuperadas em futuras chamadas, sempre identificadas.

O editor preserva as notas na biblioteca atômica Data/ai/workspace.json. **Exportar
Markdown** gera um arquivo editável fora do app; essa cópia não é sincronizada
automaticamente de volta. **Exportar plano** e a exportação JSON da conversa/sala
complementam o backup. Fonte de verdade nesta etapa é a biblioteca, não arquivos
Markdown externos.

Permissões controlam inclusão direta no contexto. Um caderno não é enviado
diretamente a outro especialista, mas uma resposta na discussão pode repetir
informações dele. Quem recebe histórico recebe essas respostas. Não existe
isolamento de informação entre participantes de uma mesma discussão pública.

## Contexto seletivo

Pergunta atual e instruções do perfil são obrigatórias. O plano completo é
obrigatório quando autorizado; se não couber, a chamada é recusada com explicação.
O orçamento é uma estimativa conservadora por bytes, incluindo reserva de saída;
não é o tokenizer do modelo.

Depois entram contribuições recentes da reunião, trocas recentes e até oito notas
pertinentes (por palavras da pergunta e recência). A conversa selecionada é enviada
em ordem cronológica, com autoria preservada. Pergunta e resposta anteriores são
selecionadas juntas; uma troca longa pode entrar como trechos sinalizados no
relatório. Não há perguntas antigas órfãs substituindo respostas que não couberam. Histórico completo continua disponível na busca da interface;
esta etapa ainda não oferece pesquisa automática de arquivos/histórico pelo modelo.
Notas propostas acima do limite são marcadas como parciais e mantêm a referência
à resposta integral.

## Execuções e avaliação

A área **Execuções** compara duas execuções, destacando diferenças de pergunta ou
revisão do plano. Mostra tempo acumulado de geração, respostas concluídas, deltas
globais amostrados de RAM/VRAM, nota humana e intervenções. A nota não é inventada
pelo sistema. Outros programas podem afetar os deltas; isso não é medição exclusiva
do processo nem benchmark de inteligência.

Cada pedido possui um identificador que impede reexecução em tentativas repetidas.
Cancelar qualquer etapa cancela a reunião inteira, incluindo o trabalho corrente.
Erro, pressão de memória ou timeout interrompem dependências. Reiniciar recupera
as reuniões pendentes como interrompidas, sem refazê-las.

O botão **Liberar modelos da memória** descarrega os modelos residentes da instância
Ollama iniciada pelo próprio Xennex, inclusive um modelo escolhido por especialista
que seja diferente do modelo global. A fila precisa estar livre. Servidores externos
continuam sob controle de quem os iniciou.

## Limites e próximas etapas

Limites atuais: 32 perfis no catálogo, oito membros por sala, três rodadas e 12
respostas por discussão, 100 execuções e 200 notas por sala, 2.000 mensagens por
sala; chats comuns mantêm limite de 200. Biblioteca: 100 conversas/salas e 16 MiB.
Fila: 20 respostas pendentes. Cada resposta tem timeout de dez minutos.

Esquema da biblioteca passou de 1 para 2. A migração mantém chats/configurações e
salva o original em workspace.json.v1.bak; o backup rotativo continua em .bak.
Executáveis anteriores não entendem o esquema novo. Dados pessoais continuam
ignorados no Git e excluídos dos pacotes públicos.

Ainda pendentes: pedidos estruturados de ajuda e convites automáticos revisáveis,
agenda dinâmica de tarefas/dependências, pesquisa de documentos e memória sob
demanda, ferramentas de leitura/escrita/terminal com concessões por escopo,
aprovações de custo, treinamento e especialistas de imagem/áudio. Texto gerado
não executa ações no computador e nenhuma API paga foi acrescentada.

## Validação

- 104 verificações de serviços: migração, fila, permissões, modelos, orçamento,
  idempotência, cancelamento e falhas de dependências.
- Interface WebView2/COM: cadastro, projeto/plano, membros/permissões, discussão,
  caderno revisado/proposto, comparação, exportação e reabertura.
- Chat simples continua validado nos protocolos compatível e Ollama nativo.
- Teste real --rooms-real llama3:latest: dois especialistas, contexto 4096,
  saída 128, orçamento 75%, cálculo de 17+25 conferido em ambas as respostas,
  reutilização dos pesos e liberação sem modelo global selecionado.
  Isso valida integração; não estabelece qualidade em projetos complexos.
Modelos adicionais e correção da continuidade: [LOCAL_AI_MODELS.md](LOCAL_AI_MODELS.md).
