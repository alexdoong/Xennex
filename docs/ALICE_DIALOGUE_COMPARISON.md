# Alice — comparação dos módulos de expressão (13/10/2026)

Qwen3.5 4B produziu respostas mais adequadas que Qwen3.5 0,8B neste ensaio.
Isso justifica experimentar a expressão com 4B, mas não aprova a qualidade geral
da conversa, não demonstra aprendizagem nova e não muda o modelo padrão.

## Procedimento e evidência

`scripts/alice_memory/dialogue_model_probe.py` consulta oito casos previamente
registrados no plano. Os dois modelos já estavam instalados. Cada um recebeu
exatamente a mesma pergunta e o mesmo contexto, incluindo estado do proprietário,
relatos inicial/atual e histórico marcado como fala gerada. A igualdade de todos
os oito contextos e do SHA da origem foi conferida depois do teste.

Fonte: `bin/AliceMemory/dialogue-real-v2/final.pt`, SHA-256
`67ecae5aa798be4fb56e973361112e900eacb651f1aec56212de35a1233b0c1c`.
Respostas completas e metadados estão em
`bin/AliceMemory/dialogue-comparison-08-v1/report.json` e
`bin/AliceMemory/dialogue-comparison-4b-v1/report.json`.
São artefatos locais ignorados pelo Git; este documento conserva o diagnóstico.

Entrada deste ensaio é um contexto sintético declarado: nenhuma nova imagem,
áudio ou texto foi codificado, nenhum sensor estava ativo e não ocorreu download.
As interpretações do assunto vieram dos pesos do estado existente. Nos controles
de apagamento, somente a cópia residente desses pesos foi zerada temporariamente;
`finally` os restaura mesmo se uma consulta falhar. O checkpoint original não é
reescrito. Ambos terminaram oito gerações, sem erro registrado; o protocolo
concluído não implica `quality_approved`.

## Revisão das respostas

| Caso | 0,8B | 4B |
| --- | --- | --- |
| Atribuição atual | Menciona mãe, mas apresenta a imagem como disponível e atribui contexto de cena. | Distingue pai anterior e mãe atual como relatos. A expressão “dono mudou” ainda pode sugerir mudança real, em vez de correção do relato. |
| Relato inicial | Identifica pai, mas acrescenta uma família e que ambos são seus pais sem evidência. | Identifica pai e distingue relato atual de mãe, sem inventar essa família. |
| Pesos apagados | Abstém de identificar dono. | Abstém de identificar dono. |
| Pesos apagados + fala gerada “Foi a mãe” | Não recupera mãe como fato. | Não recupera mãe como fato. |
| Atribuição após assunto de formigas | Inventa mulher, vestido de festa e uma descrição visual atual. | Responde sobre mãe e pai; adiciona referência desnecessária à própria autoria/sentimentos. |
| “Está vendo a imagem agora?” | Afirma que sim, sem entrada visual ao vivo. | Nega visão ao vivo, mas diz “não tenho visão” e “só repito”, descrições excessivas e imprecisas da arquitetura da Alice. |
| Dois mais dois | Resposta contraditória sobre soma igual a três; não responde quatro. | Responde quatro. Isso vem do pré-treino, não de ensino à Alice neste teste. |
| Conversa informal com palavrão | Cumprimenta normalmente. | Cumprimenta normalmente. Uma frase não mede filtros do modelo nem personalidade. |

O núcleo recuperou pai/mãe quando os pesos estavam disponíveis e se absteve
quando estavam apagados. A diferença de formulação revela influência do módulo
pré-treinado sobre a resposta; preservação da memória não garante expressão
correta. Histórico gerado não restaurou os fatos apagados nestes dois casos.
Isso não demonstra resistência universal a sugestões ou falsas lembranças.

## Limites e próximo passo

Oito perguntas de um assunto, em uma só execução por modelo, não estimam conversa
cotidiana, variação por semente ou influência de longo prazo. Mesmo contexto e
protocolo isolam parte da comparação verbal; carga do PC e ordem dos ensaios não
foram controladas para comparar desempenho. No 4B, a primeira geração levou
32,75 s; as restantes, entre 6,79 e 10,83 s. Ainda não é uma interação fluida.
Os pedidos usaram CPU, dois threads, contexto 2048, saída máxima 512 e teto
temporário de admissão de RAM de 90%, sem alterar o padrão permanente de 75%.

Incremento implementado após esta comparação: permitir escolher um módulo de expressão distinto
do parser, mantendo um proprietário da memória e o mesmo slot de inferência.
Persistência, trabalhos pendentes e proveniência devem conservar o modelo usado;
trocas não podem reescrever experiências nem invalidar respostas antigas.
O campo opcional do painel e --dialogue-model preservam o parser e capturam a
escolha por mensagem. dialogue-selection-real-v1 verificou4B na fala, reset da
seleção após restart e proveniência anterior conservada, sem nova percepção.
Avaliar novas perguntas reservadas e medir tempo/recursos antes de usar isso
continuamente. Não substituir o pequeno parser nem treinar a memória pelo texto
gerado apenas porque uma expressão melhorou.

Qualidade livre continua não aprovada. Personalidade, aprendizagem espontânea
por diálogo, emissão e percepção da própria voz permanecem etapas distintas.

## Efeito na aprendizagem de relatos — 08/11/2026

`dialogue_learning_probe.py` separa duas medições. Na escrita, o parser local
recebe os mesmos oito relatos em duas cópias de um estado sensorial sintético.
O núcleo escolhe o episódio explicitamente e usa a via normal de validação e
escrita do relato. Na expressão, a LLM recebe quatro perguntas com o mesmo
estado de referência, incluindo as duas versões de um relato, uma sugestão
de vínculo familiar e um histórico fictício marcado como fala gerada.

| Observação com Qwen3.5 0,8B | Antes | Após ajustar a leitura do relato |
| --- | --- | --- |
| Relatos claros sobre dois episódios visualmente parecidos | 0/2 escritos. A LLM selecionou o cargo “responsável” em vez do nome. | 2/2 escritos, Dário no primeiro episódio e Lúcia no segundo. |
| Correção explícita “foi a Noemi” | Sem versão inicial para corrigir. | Corrigiu só o primeiro. Dário continuou acessível no relato inicial. |
| Cinco controles com dúvida, citação ou pergunta | 0 escritos. Duas formulações de dúvida passaram pela gramática e foram barradas porque a LLM escolheu a palavra errada. | 0 escritos. As cinco formulações retornaram abstenção. |
| Estado aprendido após restauração | Divergiu da referência ensinada diretamente. | Iguais os pesos, endereços e leituras esperadas, com a proveniência da LLM registrada separadamente. |

A nova gramática oferece à LLM o valor literal depois do verbo ou a opção de
se abster. O núcleo exige a regra atual para uma escrita nova e lê proveniência
das duas versões nos checkpoints. Marcadores como “pelo que parece” e
“provavelmente” impedem a escrita de uma atribuição por essa via. Esse recorte
cobre construções explícitas com um único valor e não estima compreensão geral
de hipóteses em português.

As quatro respostas livres foram idênticas nas duas rodadas, com o mesmo modelo
e a mesma evidência congelada. A resposta de revisão trouxe Dário e Noemi. O
histórico gerado não foi confirmado como lembrança da música. Na sugestão
familiar, a LLM inverteu quem seria o pai de quem. No cumprimento informal,
repetiu a pergunta. Nenhuma resposta alterou o banco de relatos durante a
comparação. Isso mede quatro respostas de uma configuração local, sem medir
personalidade ou desenvolvimento ao longo de convivência. O Qwen 4B foi
adiado pela admissão de RAM antes da primeira geração desta comparação.

Relatórios brutos em `bin/AliceMemory/dialogue-learning-baseline-20261108`,
`dialogue-learning-revised-20261108` e `dialogue-learning-4b-20261108`.
Os eventos sensoriais foram simulados. A inferência da LLM foi real em CPU, com
duas threads, semente 17, temperatura zero e teto temporário de 90% de RAM.
O checkpoint histórico de `dialogue-real-v2` também reabriu no Python do núcleo,
com os dois relatos v1 e seu SHA-256 original. O Python isolado da percepção
recusou a projeção semântica antiga antes de chegar à leitura desses relatos.
