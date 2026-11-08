# Evolução do modo compacto

## Concluído em 26/09/2026

O plano anterior deixou de ser pendente. Foram implementados:
- Separação de posição aberta e direção de recolhimento.
- Alça nas bordas reais, inclusive superior, sem invadir o monitor vizinho.
- Auto pela borda mais próxima, geometria estável e animação baseada em tempo.
- Navegação e interfaces compactas por área com controllers compartilhados.
- Chat selecionado e rascunhos compartilhados entre IA compacta e completa.
- Editor de skins completo dentro do painel, com prévia e salvamento.
- Testes de geometria/movimento, WPF, navegador e aplicativo real com WebView2.

Consulte COMPACT_MODE.md para comportamento, arquivos e comandos.
Não há necessidade de reconstruir essa infraestrutura a partir do plano antigo.

## Próximos incrementos possíveis

- Refinar a composição de cada área conforme o uso real, mantendo Expandir
  para fluxos complexos (edição de estratégias, salas com múltiplos agentes etc.).
- Unificar também rascunhos específicos de registros de jogos entre as duas
  apresentações, se o fluxo completo passar a editar o mesmo registro.
- Avaliar atalhos e organização personalizável dos cartões.
- Medir fluidez percebida e conferir fisicamente monitores com escalas distintas.
- Avaliar se a opção da skin Reduzir animações deve controlar também a animação
  nativa; atualmente ela controla CSS/fundo, e a janela respeita o Windows.

Esses incrementos não estão prometidos como parte da correção atual.
