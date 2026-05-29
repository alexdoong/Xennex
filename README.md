# Xennex

Personal environment nexus for Windows, driver management, and gaming utility tools



\---



Status: Alpha do Alpha (Primeiríssima Versão)



Este repositório registra o Marco Zero Absoluto de todo o projeto. O código aqui reflete a primeira coisa real e física que foi realizada: um rascunho funcional e bruto feito para centralizar automações que antes ficavam espalhadas em arquivos soltos.



É um protótipo experimental, focado puramente em validar a ideia e ver o dashboard funcionando na prática pela primeira vez.



\---



O que este primeiro código faz?



Atualmente, o nexo é composto por uma única ferramenta integrada: o Wacom \& Audio Latency Controller. (O painel já conta também com uma aba dedicada para Wuthering Waves, por conta que já tinha uma ideia que queria algo que me ajudasse em tudo)



A interface gráfica direta (C# WinForms) gerencia duas funções essenciais que rodam no Windows:



1\. Controle dos Drivers Wacom: Dispara os arquivos .bat para ativar/desativar os serviços de hardware direto pela interface (com elevação de Admin).

2\. Esconder o REAL.exe:\*\* Inicializa o motor de redução de latência de áudio em segundo plano, capturando as linhas de texto que ele gera e transmitindo dentro de uma caixinha de log interna. Isso elimina a necessidade de manter janelas pretas de terminal abertas na tela.



\---



Como Compilar (Direto no Windows)



Como é a versão mais básica possível, você não precisa de nenhum programa de desenvolvimento ou IDE instalado. A compilação usa o próprio motor nativo do Windows (csc.exe).



1\. Configuração do Motor de Áudio: O arquivo REAL.exe pode ser adicionado posteriormente. Inclusive, o recomendado é adicioná-lo depois, pois dentro do app você consegue colocar o caminho para o REAL.exe diretamente.

2\. Clique com o botão direito em `compile.bat` e execute como Administrador.

3\. O executável bruto `WacomRealController.exe` vai aparecer na raiz na mesma hora.



\---



Arquivos da Primeira Versão



Estes são os arquivos exatos que dão vida ao primeiro formato do projeto:



```text

├── Program.cs               # O código-fonte bruto em C#

├── compile.bat              # Script que chama o compilador nativo do Windows

├── DisableWacomDrivers.bat  # Script antigo que desativa os drivers

├── EnableWacomDrivers.bat   # Script antigo que ativa os drivers

├── REAL.exe                 # O motor de redução de latência de áudio (opcional no diretório)

├── WacomRealController.exe  # O programa gerado após rodar o compile.bat

├── config.txt               # Onde o app guarda os caminhos locais configurados

└── team\_config.txt          # Configurações específicas da minha máquina

