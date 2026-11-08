# Usar a IA local

## Disponível nesta etapa

No build de desenvolvimento, **IA local → Alice experimental** controla o núcleo
experimental separado do chat. Selecione o Python com dependências, um estado .pt
compatível e o endpoint/modelo local instalado. O estado é copiado na primeira
sessão; retomar usa Data/ai/alice sem reimportar ou alterar a origem. O estado
inicial do zero ainda não é oferecido neste painel.

**Modelo de conversa (opcional)** escolhe a expressão de **Conversar** separadamente
do **Modelo instalado**, que continua interpretando ensinamentos e consultas.
Por exemplo: manter qwen3.5:0.8b-q8_0 em **Modelo instalado** e usar qwen3.5:4b na conversa.
Vazio usa o mesmo modelo nos dois. Configure com a sessão parada; mensagens já
recebidas conservam sua escolha, inclusive após retomar. Ambos usam o mesmo slot
de inferência e a mesma memória; o painel não baixa pesos. O 4B melhorou alguns
casos avaliados, mas pode errar e ainda apresentou latência em CPU.

Para enviar experiências, selecione também o Python isolado da percepção e a
pasta do encoder instalado. PNG, WAV e TXT são enviados apenas quando escolhidos.
Selecione a experiência para ensinar nome/relação, ou uma mensagem anterior para
corrigir/consultar. Linguagem ainda delimitada: exemplos como “Essa imagem se chama
Hami”, “O autor dessa imagem é meu pai”, correção “É minha mãe” e consulta “E agora?”.
Confira o resultado; receber uma mensagem não comprova aprendizado bem-sucedido.

**Enviar imagem e áudio juntos** registra um PNG e um WAV selecionados como um
único momento. Para ensinar um nome visual, selecione essa experiência, escolha
**Imagem** como referência do nome e escreva algo como “Essa imagem se chama
Maruvi”. Com evocação implícita habilitada, um áudio enviado depois pode evocar
o nome aprendido pela visão. **Estado salvo da memória** mostra a associação
quando ela tem apoio em episódios anteriores. Os clipes são arquivos
selecionados, e a simultaneidade do par é declarada por quem o envia.

**Palavras faladas · experimental** aceita um WAV contendo uma única palavra.
Digite a grafia em **Palavra escrita** e selecione **Ensinar pronúncia**. Em
**Tentar reconhecer palavra**, escolha outro WAV para testar o que ficou
aprendido. Pode-se ensinar outro exemplo da mesma palavra com uma voz diferente.
O recurso mostra o resultado só quando o áudio correspondente foi processado.
No terminal, `send_native_frame --audio ARQUIVO --word-audio --name PALAVRA`
ensina e a mesma opção sem `--name` consulta. O resultado também está no recibo
do inbox. [Resultados e limites](ALICE_EPISODIC_CONTEXT.md#aprender-o-som-de-palavras-isoladas)

**Conversar · experimental** envia a mensagem também ao encoder de texto; precisa
da percepção configurada. Um relato selecionado opcionalmente fornece a memória
do assunto. A fala é gerada pelo modelo pré-treinado e aparece após confirmação;
o texto da memória é mostrado separadamente. O modelo pequeno ainda pode misturar
assuntos e errar conhecimento geral. Falas geradas não são ensinamentos automáticos,
nem percepção da própria voz. Encoder recarregado por entrada também pode causar
latência; este fluxo é experimental e não representa ainda convivência cotidiana.

Quando nenhum relato é selecionado, o build de desenvolvimento tenta evocar uma
associação por um nome já aprendido na mensagem adquirida. Esse recorte exige
episódio e relação únicos; o ensaio com a memória real encontrou ambiguidade e
a integração com nova entrada ficou pendente por RAM. Ainda não é evocação geral
por contexto, nem acesso integrado a acontecimentos/detalhes. Seleção explícita
continua disponível; a fala livre pode errar mesmo com memória correta.

Em **Atenção na percepção**, a opção aprendida ativa uma política experimental que
pode selecionar modalidades ou não adquirir o sinal. **Avaliar uma escolha de
atenção** permite selecionar uma decisão válida dos últimos60s e dar retorno como
“Gostei disso” ou “Não gostei disso”. Aprovar quiet também é válido: não cria uma
lembrança sensorial. Escolhas já avaliadas/vencidas saem da lista; a avaliação não
confirma fatos sobre o mundo. O aprendizado de atenção ainda precisa ser avaliado
em situações cotidianas além do laboratório.

**Parar e salvar Alice** encerra a sessão explicitamente; fechar o painel mantém
o processo iniciado. Encerrar o aplicativo também pede parada/salvamento.0 segundos
mantém sessão até parar; orçamento90% somente em teste finito. Não há autostart,
câmera/microfone, conversa cotidiana validada ou download automático. Consulte
[plano e limitações](ALICE_DEVELOPMENT_PLAN.md) para o estado dessa implementação.

### Recortes visuais na Alice

Em Windows x64, configure **Pasta do Mirage para recortes automáticos (opcional)**
com uma pasta contendo `libcactus.dll` e `mirage.cact`. O worker confere os SHA-256
da DLL do wheel Windows x64 do Cactus 4.0.0 e dos pesos Mirage de 2 bits. A pasta
fica vazia por padrão. O runtime usa os arquivos locais e executa o detector no
worker finito da percepção. A alternativa no terminal é `--native-mirage PASTA`
no comando do runtime. [Runtime Cactus](https://huggingface.co/Cactus-Compute/cactus)
· [Pesos Mirage](https://huggingface.co/Cactus-Compute/mirage)

Selecione as imagens como de costume. Em **Estado salvo da memória**, o painel
mostra os momentos com recortes retidos e o resultado da última detecção. Se o
detector estiver indisponível ou devolver apenas caixas que ocupam quase toda a
imagem, a cena inteira segue para a atenção. Os recortes são avaliados como
pistas visuais e ficam sujeitos à atenção e ao critério de evocação.

O publicador do inbox sensorial local permite anexar até quatro regiões a uma
imagem durante uma sessão configurada. Cada caixa em pixels usa a ordem
esquerda, topo, direita e base. As bordas direita e inferior são exclusivas.
Caixas explícitas ou importadas têm prioridade sobre a detecção automática.

```powershell
& $pythonAlice -m scripts.alice_memory.send_native_frame --inbox $inboxAlice --image $imagem --region 30 40 180 210
```

O mesmo comando aceita `--mirage-result $json` em vez de `--region`. O JSON pode
ser produzido separadamente, em um ambiente que já tenha o Mirage configurado.
O digest deve ser calculado sobre os mesmos bytes que o detector recebeu.

```python
import hashlib
import json
from pathlib import Path

import cactus

image = Path("image.png").read_bytes()
result = cactus.Mirage().describe(image, sections=["objects"], fields=["bbox", "score"], max_objects=16)
Path("mirage.json").write_text(json.dumps({
    "image_sha256": hashlib.sha256(image).hexdigest(),
    "result": result,
}), encoding="utf-8")
```

O comando da Alice lê o JSON e a imagem localmente. O exemplo em Python usa
o SDK do Cactus e seus pesos. Com a evocação implícita habilitada, recortes
recebidos pelo inbox podem apontar para momentos anteriores e recuperar os sinais
associados. [Contrato de memória visual](ALICE_EPISODIC_CONTEXT.md)

### Conversas e especialistas

Conversas com histórico, streaming, exportação JSON, rascunhos entre abas, fila
serial, cancelamento e proteção por RAM/VRAM. O limite padrão é 75% do consumo
total de cada memória. Priorizar meu PC interrompe a resposta e pausa a fila.

Ollama possui integração nativa: detectar/iniciar motor, consultar modelos em
disco e carregados, configurar contexto, CPU e permanência na memória. A API
compatível com OpenAI continua disponível para outros motores, como LM Studio.
Nenhum modelo é baixado pelo Xennex; o motor e os pesos são dependências opcionais.
Não há cobrança nem integração com serviços pagos nesta etapa.

Salas com especialistas, plano editável, cadernos individuais e reuniões limitadas
já estão disponíveis. Veja [Salas e especialistas](LOCAL_AI_ROOMS.md) para configurar
a equipe e comparar execuções. Ferramentas, pesquisa, áudio e treinamento continuam
no [plano](LOCAL_AI_PLAN.md). Respostas ainda não executam código, abrem arquivos
ou alteram o computador.

## Conectar Ollama

1. Abra **IA local → Conexão e orçamento**.
2. Use **Detectar Ollama** se já existir um servidor, ou **Iniciar Ollama pelo
   Xennex** para usar a instalação padrão do Windows.
3. Clique no cartão do modelo instalado. Isso preenche a configuração como
   Ollama nativo e ativa a estimativa automática; confirme em **Salvar configuração**.
4. Abra uma conversa e envie a mensagem. Se faltar margem, a fila mostra o motivo.

A detecção verifica o endereço salvo, 127.0.0.1:11434 e a instância privada em
127.0.0.1:11436. Ela não procura servidores na rede. Instalações fora do caminho
padrão podem ser iniciadas manualmente e conectadas pelo campo de endereço.

A instância iniciada pelo Xennex usa OLLAMA_NO_CLOUD=1, uma execução e um modelo
carregado por vez. Seu processo encerra com o app. Nenhum servidor que já estava
aberto é adotado ou encerrado pelo Xennex. O botão **Liberar modelos da memória**
fica disponível apenas para a instância iniciada pelo app, com a fila vazia.
A lista de modelos mostra a hora da consulta; Detectar Ollama atualiza o estado.

No modo nativo, a integração confere pesos locais e capacidade de conversa antes
de enviar o histórico. Modelos identificados como remotos são recusados. Usar
loopback não prova que um servidor arbitrário não seja um proxy: configure motores
externos para inferência local. Não há autenticação por token nesta versão.

## Outros motores

Selecione **API compatível — configuração manual**, salve o endereço e consulte
os modelos no endereço salvo. Escolha o identificador e salve novamente.
Exemplo de LM Studio: http://127.0.0.1:1234/v1. Somente HTTP com IP loopback literal
127.0.0.1 ou ::1 é aceito; não há redirecionamentos ou destinos externos.
Configurações antigas permanecem nesse modo e conservam suas reservas manuais.

## Memória, contexto e permanência

No Ollama, **Estimar com os dados do modelo** usa /api/tags, /api/ps e /api/show:

- Modelo não residente: tamanho em disco com margem, estimativa de KV cache e
  buffers. Reserva conservadora em RAM e, no modo GPU, também em VRAM.
- Mesmo modelo, contexto e modo já carregados: pesos já estão no uso global;
  reserva inicialmente 1 GiB extra por memória monitorada.
- Metadados de cache ausentes usam uma aproximação conservadora. Alocação
  desconhecida ou contexto diferente não recebem o desconto de residência.
- Aumentos amostrados durante execuções anteriores podem elevar futuras reservas.
  São deltas globais, não medições exatas do processo: outros apps podem contribuir.
  Até 64 perfis são persistidos por endpoint, modelo/digest, contexto, modo e residência.
  As observações nunca reduzem a reserva base. A opção manual permanece disponível.

As estimativas não garantem o pico de consumo. Não há reserva física de memória,
limite de utilização de CPU/GPU, controle de temperatura ou previsão de duração.
Com outras aplicações abertas, até um modelo que cabe sozinho pode ficar na fila.
Não aumente o orçamento automaticamente para fazê-lo caber; reduza o contexto,
use um modelo menor ou libere memória de aplicações que não estiver usando.

Contexto é configurável entre 2048 e 16384 tokens, respeitando a capacidade do
modelo. O modo nativo envia num_ctx e num_predict explicitamente e usa uma
estimativa conservadora por bytes para recusar conversas grandes antes do envio.
Essa checagem não é o tokenizer do modelo. Conversas simples grandes são recusadas;
abra outra conversa com um resumo quando necessário. Salas selecionam contexto com
um relatório por resposta, preservando o histórico completo em disco.

No modo CPU nativo, o pedido envia num_gpu=0. Na API compatível, o modo CPU apenas
muda a política de admissão: configure a execução também no próprio motor.
A GPU monitorada é o adaptador dedicado com maior memória; multi-GPU ainda não
é suportado pela política.

Permanência de 0 segundos solicita descarregar após cada resposta. Entre 1 e 300
segundos permite reutilizar o modelo entre mensagens. Cancelar HTTP ou pressionar
Priorizar meu PC não garante liberação imediata de pesos. Pressão de memória
interrompe a solicitação, preserva o texto parcial e pausa a fila; retomar não
repete a mensagem interrompida.

## Histórico e validação

Dados privados em Data/ai/workspace.json, gravação atômica e backup .bak; não entram
no pacote público. Limites: 100 conversas, 200 mensagens por conversa simples (2000 por sala), 20 trabalhos
pendentes, 16 MiB no histórico, 10 minutos por resposta. Há também um limite geral
de 24 mil caracteres de contexto. Checkpoints parciais ocorrem a cada 3 segundos
quando chegam tokens. Reiniciar não repete trabalhos anteriores.

Validação da base em 19/09: 60 verificações automatizadas, interface WebView2/COM com
servidor controlado nos dois protocolos e restauração após reinício. No PC de
desenvolvimento, llama3:latest respondeu a duas perguntas aritméticas, reutilizou
o modelo na segunda chamada e confirmou descarregamento. O teste usou contexto
2048, saída 128 e limite 85%, em dados isolados; não alterou o padrão de 75%.
Reserva estimada: 6,24 GiB por memória no carregamento, 1 GiB com modelo residente.
Esses valores não são um benchmark de qualidade ou garantia para outros cenários.
O incremento de salas amplia a suíte para 104 verificações, com integração nativa
e duas respostas reais sequenciais sob o orçamento padrão de 75%.
Veja [TESTING.md](TESTING.md) para reproduzir os testes.

Referências do protocolo: [chat](https://docs.ollama.com/api/chat),
[modelos carregados](https://docs.ollama.com/api/ps) e
[configuração e permanência](https://docs.ollama.com/faq).
Consulte [Modelos e aprendizado](LOCAL_AI_MODELS.md) para os modelos preparados,
a correção da continuidade da conversa e o uso de notas revisadas.
