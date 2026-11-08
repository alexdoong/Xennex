# Hub de rotina e vida — integração futura

Registrado em 2026-09-13 a pedido do usuário. Planejamento; integração ainda não iniciada.

## Origem e intenção

O usuário já mantém um hub no Google AI Studio, acessível somente pela web.
Ele funciona como um calendário dinâmico para rotina, trabalho, atividades,
conteúdos consumidos, coisas realizadas e planejadas. No futuro, pretende trazer
esse projeto para dentro do Xennex. O código e os dados desse hub ainda não foram
inspecionados; não presumir seu framework, armazenamento ou modelo de autenticação.

A área de jogos e o hub têm uma intenção comum: registrar experiências no tempo,
organizar informação e apoiar análises e decisões. A futura Alice também faz
parte da visão do usuário, mas sua interface de integração ainda não foi definida.

## Direção de arquitetura

- Manter domínios próprios: jogos, rotina/vida e assistência da Alice.
- Compartilhar componentes de calendário, linha do tempo, filtros, notas,
  métricas e referências quando os contratos reais justificarem esse reuso.
- Não converter tarefas, compromissos e conteúdos de vida em partidas ou jogos.
- Preservar diferença entre evento realizado, plano, tarefa pendente e simulação.
- Recorrência, fusos horários, conclusão e reagendamento serão regras do hub.
- A biblioteca de jogos deve funcionar independentemente dessa migração.
- Dados pessoais e eventuais credenciais permanecem fora do Git e dos pacotes.

## Quando a migração começar

1. Inspecionar o projeto web e seu formato de armazenamento/exportação.
2. Mapear os fluxos que o usuário já utiliza e manter um backup exportável.
3. Definir o que permanece web, o que funciona offline e o que exige serviços.
4. Planejar importação versionada com validação e preservação de datas e vínculos.
5. Integrar a interface no padrão React/WebView2 do Xennex, sem concentrar lógica
   de negócio no ApiBridge ou na janela WPF.
6. Só então avaliar uma visão transversal de jogos e vida, com filtros explícitos.

O trabalho atual permanece na primeira etapa da análise de jogos.
