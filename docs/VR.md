# Biblioteca no SteamVR

Atualizado em 05/10/2026. A Biblioteca tem um painel 2D próprio no SteamVR,
renderizado em memória, sem capturar o desktop ou executar arquivos.
Reutiliza o catálogo, IDs opacos e validação de caminhos do Xennex.

## Como abrir e navegar

1. Abra SteamVR/Meta Link com o Rift S conectado e o Xennex atualizado.
2. Na Biblioteca, clique em **Abrir no VR**. A opção padrão é **Biblioteca
   completa — começar na visão atual**; não precisa selecionar imagens.
   Os filtros e a pasta atuais são mantidos ao abrir.
3. Confira **Minimizar o Xennex à bandeja após abrir no VR** e clique em
   **Abrir no SteamVR**. A janela só é escondida após conectar com sucesso.
4. No dashboard, abra a aba **Xennex · Biblioteca**. Aponte o laser e use o
   gatilho. **Galeria** mostra miniaturas de imagens, incluindo subpastas;
   **Explorador** lista imagens, arquivos e pastas da localização imediata.
5. **Acervos** permite escolher qualquer pasta já cadastrada no desktop e
   limpa os filtros anteriores ao entrar nela. Clique numa pasta para entrar;
   **Pasta acima** sobe um nível. **Favoritos**, ordenação por nome/data e
   **Atualizar** alteram a visão sem sair do headset. Atualizar relê o catálogo;
   não inicia uma nova varredura do disco.
6. **Anterior/Próxima página** percorre grupos de 12 entradas. Clique numa
   imagem para ampliá-la. No visualizador, **Anterior/Próxima** percorre as
   imagens da consulta, inclusive entre páginas. Os botões ficam desativados
   quando não há outra imagem. **Voltar** retorna à página onde abriu a imagem.
7. **Tamanho** abre ajustes de largura (0,75–3 m) e distância (0,75–3 m).
   O painel começa com 2 m de largura, em vez dos 1,4 m do protótipo.
   Esses ajustes são independentes do zoom da imagem. A distância vale para
   o painel **Fixado**; no dashboard a posição é administrada pelo SteamVR.
   **Voltar** fecha os ajustes preservando a imagem/pasta. Não persistem entre sessões.
8. **Fixar** posiciona o painel à frente do headset, inicialmente a 1,5 m;
   feche o dashboard para usá-lo no espaço. **Centralizar** atualiza sua posição.
   **Fechar** no headset ou **Encerrar VR** no desktop libera a sessão.

A opção **Seleção atual** continua disponível: abre somente as imagens
selecionadas, ou as disponíveis na página atual quando não há seleção, até
100 imagens. Uma pasta selecionada não é convertida implicitamente numa
lista de imagens: use Biblioteca completa para navegar por ela no headset.
Fechar as opções no desktop mantém a sessão VR aberta. Encerrar a sessão
não revela automaticamente as artes na janela do monitor.

## Contratos e limites

`StartAssetVr(json)` aceita `mode: selection` (compatibilidade com o protótipo),
`assetIds` e `initialId`, ou `mode: library`, `view: gallery|explorer` e uma
`query` do catálogo. `GetAssetVrState`, `ControlAssetVr(action)` e `StopAssetVr`
expõem estado e comandos. A consulta reutiliza `AssetLibraryService.Query`.
Não há limite de 100 imagens no catálogo navegável; carrega até 12 entradas
por página. Acervos também são paginados. Edição de tags, cadastro de pastas,
coleções e operações físicas de arquivos continuam no desktop; seus filtros
atuais podem ser enviados ao abrir o painel.

O worker mantém OpenVR, decodificação e renderização fora da thread da janela.
O quadro é limitado a 1280×800 RGBA e só é enviado quando muda a apresentação.
Miniaturas usam o cache existente; novas miniaturas e prévias têm ambas as
dimensões limitadas antes de alocar pixels (360 e 1600, respectivamente).
Arquivos sem prévia e imagens indisponíveis mostram um aviso. GIF mostra um
quadro estático. Não há vídeos, zoom por arraste, teclado de busca no headset
ou migração das outras abas WPF/WebView2 para VR.

Entrada guarda a posição de `MouseMove` por overlay/cursor. Os eventos de
botão podem não trazer coordenadas válidas, como no exemplo oficial da Valve;
o clique é confirmado ao soltar o gatilho sobre o mesmo alvo onde apertou.
Renderização e hit testing usam os mesmos retângulos de controles.

Dependência: SteamVR instalado e em execução. O binding C# da Valve está
vendorizado sem alterações, com licença BSD, na revisão
`0924064316de3effbcd1acf1e309182a2deb1c05`. A DLL OpenVR é carregada somente
do runtime SteamVR registrado; não procurar DLL arbitrária nem baixar binários
na inicialização. Não alterar configurações Meta/SteamVR. O dashboard é dono
da miniatura: destruir o dashboard libera também sua miniatura.

Privacidade: o Xennex não cria um espelho no monitor. A flag OpenVR de conteúdo
protegido limita leituras da textura, mas não garante invisibilidade contra
Oculus Mirror, captura do compositor, outros programas ou acesso ao PC.
O usuário aceita deixar o espelho em outra área de trabalho.

## Verificação

```powershell
dotnet run --project scripts/tests/VrTests/VrTests.csproj -c Release
# Opcional, com SteamVR aberto: usa somente imagens sintéticas temporárias.
dotnet run --project scripts/tests/VrTests/VrTests.csproj -c Release -- --native
```

Testes determinísticos entram no CI e cobrem eventos sem coordenadas no
release, isolamento de cursores, seleção de uma imagem, catálogo de 126
imagens, miniaturas, páginas, pastas, retorno, favoritos, tamanho/distância,
RGBA, ciclo de vida, falha e cancelamento. Prévia visual sintética em `bin/vr-ui/`.
O smoke nativo verifica envio das texturas, galeria, sequência de imagens,
acervos, explorador, fixação, tamanho, distância, encerramento e reabertura.
Não confirma cliques físicos, conforto ou comportamento do espelho.

Em 03/10 o usuário confirmou o painel sintético no headset. Em 05/10 corrigiu
o relato inicial: anterior/próxima já funciona com várias imagens selecionadas;
a falta principal era navegar livremente no catálogo e aumentar o painel.
A seleção original não incluía recursivamente pastas. A nova opção padrão
Biblioteca completa cobre essa navegação, mantendo Seleção atual explícita.

Referências oficiais: [overlays](https://github.com/ValveSoftware/openvr/wiki/IVROverlay_Overview),
[exemplo de entrada](https://github.com/ValveSoftware/openvr/blob/master/samples/helloworldoverlay/openvroverlaycontroller.cpp),
[bindings](https://github.com/ValveSoftware/openvr/blob/0924064316de3effbcd1acf1e309182a2deb1c05/headers/openvr_api.cs),
[Oculus Mirror](https://developers.meta.com/vr/documentation/native/pc/dg-compositor-mirror/).
