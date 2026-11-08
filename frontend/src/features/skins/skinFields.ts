import type { SkinConfig } from '../../webview';

export interface SkinField {
  key: keyof SkinConfig; label: string; section: string;
  kind: 'range' | 'color' | 'select' | 'check' | 'asset';
  min?: number; max?: number; step?: number; options?: [string, string][];
}
const range = (key: keyof SkinConfig, label: string, section: string, min: number, max: number, step = 1): SkinField => ({ key, label, section, kind: 'range', min, max, step });
const color = (key: keyof SkinConfig, label: string, section = 'Cores'): SkinField => ({ key, label, section, kind: 'color' });
export const SKIN_FIELDS: SkinField[] = [
  { key: 'backgroundType', label: 'Tipo de fundo', section: 'Fundo', kind: 'select', options: [['image','Imagem'],['video','Vídeo'],['color','Cor'],['gradient','Degradê']] },
  { key: 'backgroundUrl', label: 'Imagem ou vídeo do fundo', section: 'Fundo', kind: 'asset' },
  color('backgroundColor','Cor de fundo','Fundo'), color('gradientColor','Segunda cor do degradê','Fundo'),
  range('gradientAngle','Ângulo do degradê','Fundo',0,360),
  { key: 'backgroundFit', label: 'Enquadramento', section: 'Fundo', kind: 'select', options: [['cover','Preencher sem distorcer'],['contain','Mostrar inteiro'],['fill','Esticar']] },
  range('backgroundPositionX','Posição horizontal','Fundo',0,100), range('backgroundPositionY','Posição vertical','Fundo',0,100),
  range('backgroundOpacity','Opacidade do fundo','Fundo',0,1,.01), range('backgroundBlur','Desfoque do fundo','Fundo',0,32),
  range('backgroundBrightness','Brilho','Fundo',0,200), range('backgroundSaturation','Saturação','Fundo',0,200),
  color('overlayColor','Cor da sobreposição','Fundo'), range('overlayOpacity','Opacidade da sobreposição','Fundo',0,1,.01),
  { key: 'pauseBackgroundVideo', label: 'Pausar vídeo de fundo', section: 'Fundo', kind: 'check' },
  color('primaryColor','Cor principal'), color('primaryHover','Cor ao passar o mouse'),
  color('textColor','Texto principal'), color('secondaryTextColor','Texto secundário'), color('buttonTextColor','Texto dos botões'),
  color('inputColor','Fundo dos campos'), color('panelColor','Cor dos painéis','Painéis'),
  range('panelOpacity','Opacidade dos painéis','Painéis',0,1,.01), range('panelBlur','Desfoque dos painéis','Painéis',0,32),
  range('glassHighlight','Reflexos do Liquid Glass','Painéis',0,1,.01),
  range('panelRadius','Cantos dos painéis','Painéis',0,48), range('panelPadding','Espaço dentro dos painéis','Painéis',0,48),
  range('shadowStrength','Intensidade das sombras','Painéis',0,1,.01), range('buttonRadius','Cantos dos botões','Painéis',0,48),
  color('borderColor','Cor das bordas','Painéis'), range('borderOpacity','Opacidade das bordas','Painéis',0,1,.01), range('borderWidth','Espessura das bordas','Painéis',0,4),
  color('cardColor','Cor dos cartões internos','Cartões'), range('cardOpacity','Opacidade dos cartões','Cartões',0,1,.01),
  color('cardBorderColor','Cor da borda dos cartões','Cartões'), range('cardBorderOpacity','Opacidade da borda dos cartões','Cartões',0,1,.01),
  range('cardRadius','Cantos dos cartões','Cartões',0,48), range('cardPadding','Espaço interno dos cartões','Cartões',0,48),
  range('cardGap','Espaço entre cartões','Cartões',0,48),
  { key:'settingsColumns',label:'Colunas em Configurações',section:'Estrutura',kind:'select',options:[['1','Uma coluna'],['2','Duas colunas']] },
  color('sidebarColor','Cor da barra lateral','Barras'), { key:'sidebarImage', label:'Imagem da barra lateral',section:'Barras',kind:'asset' },
  range('sidebarImageOpacity','Opacidade da imagem lateral','Barras',0,1,.01), range('sidebarWidth','Largura da barra lateral','Barras',56,100),
  range('sidebarRadius','Cantos da barra lateral','Barras',0,48),
  color('titlebarColor','Cor da barra superior','Barras'), { key:'titlebarImage',label:'Imagem da barra superior',section:'Barras',kind:'asset' },
  range('titlebarImageOpacity','Opacidade da imagem superior','Barras',0,1,.01), range('barBlur','Desfoque das barras','Barras',0,32),
  range('windowRadius','Cantos da janela','Layout',0,48), range('contentScale','Escala do conteúdo (%)','Layout',80,130),
  range('contentPadding','Margens do conteúdo','Layout',0,48), range('scrollbarWidth','Largura da rolagem','Layout',4,16),
  color('scrollbarColor','Cor da rolagem','Layout'),
  { key:'navigationPlacement',label:'Navegação',section:'Estrutura',kind:'select',options:[['left','Esquerda'],['right','Direita'],['bottom','Embaixo']] },
  { key:'controlsPlacement',label:'Controles da janela',section:'Estrutura',kind:'select',options:[['left','Esquerda'],['center','Centro'],['right','Direita']] },
  { key:'windowPresentation',label:'Área da janela',section:'Estrutura',kind:'select',options:[['floating','Painéis flutuantes'],['filled','Preencher a janela']] },
  { key:'surfaceStyle',label:'Acabamento',section:'Estrutura',kind:'select',options:[['glass','Vidro'],['liquid','Liquid Glass'],['solid','Sólido'],['terminal','Terminal'],['ornate','Ornamentado']] },
  { key:'fontFamily',label:'Fonte',section:'Layout',kind:'select', options:[['system','Sistema / Inter'],['segoe','Segoe UI'],['mono','Monoespaçada']] },
  { key:'reducedMotion',label:'Reduzir animações e pausar o fundo',section:'Layout',kind:'check' },
];
export const SKIN_PRESETS: { name: string; description: string; patch: Partial<SkinConfig> }[] = [
  { name:'Liquid Moon', description:'Vidro azul noturno, reflexos suaves e bordas de luar', patch:{
    navigationPlacement:'left', controlsPlacement:'right', windowPresentation:'floating', surfaceStyle:'liquid',
    backgroundType:'gradient', backgroundColor:'#070e1d', gradientColor:'#213657', gradientAngle:145,
    overlayColor:'#050b17', overlayOpacity:.12, backgroundOpacity:1, backgroundBlur:0,
    backgroundBrightness:100, backgroundSaturation:100,
    panelColor:'#101d34', panelOpacity:.78, panelBlur:22, glassHighlight:.55,
    panelRadius:24, panelPadding:24, buttonRadius:14, windowRadius:26, shadowStrength:.35,
    sidebarColor:'rgba(10,20,38,0.74)', titlebarColor:'rgba(10,20,38,0.66)', barBlur:20,
    sidebarImageOpacity:.18, titlebarImageOpacity:.18, sidebarRadius:24,
    primaryColor:'#90bcff', primaryHover:'#b3d2ff', textColor:'#edf3ff', secondaryTextColor:'#afbed2',
    buttonTextColor:'#0b1930', inputColor:'#091427', borderColor:'#dac9a2', borderOpacity:.3, borderWidth:1,
    cardColor:'#142443', cardOpacity:.46, cardBorderColor:'#d1def5', cardBorderOpacity:.2,
    cardRadius:18, cardPadding:22, cardGap:20, fontFamily:'segoe', contentPadding:26,
    scrollbarColor:'#6f86a6' } },
  { name:'Gryphlink', description:'Vidro flutuante e navegação lateral', patch:{
    navigationPlacement:'left', controlsPlacement:'right', windowPresentation:'floating', surfaceStyle:'glass',
    panelBlur:16, panelOpacity:.86, panelRadius:24, buttonRadius:12, windowRadius:20, fontFamily:'system',
    primaryColor:'#a56aff', primaryHover:'#c09aff', backgroundColor:'#0f131a', panelColor:'#121826',
    backgroundType:'color', sidebarColor:'#121826', titlebarColor:'#121826',
    cardColor:'#ffffff', cardOpacity:.05, cardBorderColor:'#ffffff', cardBorderOpacity:.08, cardRadius:16, cardPadding:24, cardGap:24,
    textColor:'#f4f3fa', secondaryTextColor:'#aab2c4', inputColor:'#10131c', borderColor:'#ffffff', borderOpacity:.25 } },
  { name:'Merlin', description:'Tons de pergaminho e moldura ornamental', patch:{
    navigationPlacement:'right', controlsPlacement:'center', windowPresentation:'filled', surfaceStyle:'ornate',
    backgroundType:'gradient', backgroundColor:'#211b18', gradientColor:'#493724', panelColor:'#30251d',
    sidebarColor:'#30251d', titlebarColor:'#30251d',
    cardColor:'#5a422b', cardOpacity:.55, cardBorderColor:'#d7ad63', cardBorderOpacity:.55, cardRadius:10, cardPadding:24, cardGap:20,
    panelOpacity:1, panelBlur:0, panelRadius:10, buttonRadius:8, windowRadius:10, fontFamily:'segoe',
    primaryColor:'#d7ad63', primaryHover:'#eccb8c', textColor:'#f6e9cf', secondaryTextColor:'#c7b89c',
    buttonTextColor:'#211b18', inputColor:'#1c1816', borderColor:'#c79b57', borderOpacity:.75, borderWidth:2 } },
  { name:'Terminal', description:'Monoespaçado, superfícies sólidas e cantos retos', patch:{
    navigationPlacement:'bottom', controlsPlacement:'left', windowPresentation:'filled', surfaceStyle:'terminal',
    backgroundType:'color', backgroundColor:'#090e0b', panelColor:'#0d1710', panelOpacity:1, panelBlur:0,
    sidebarColor:'#0d1710', titlebarColor:'#0d1710',
    cardColor:'#102017', cardOpacity:1, cardBorderColor:'#4ac576', cardBorderOpacity:.65, cardRadius:0, cardPadding:18, cardGap:16,
    panelRadius:0, buttonRadius:0, windowRadius:0, fontFamily:'mono', primaryColor:'#5fe28c', primaryHover:'#93f4b4',
    textColor:'#c4f8cf', secondaryTextColor:'#87b898', buttonTextColor:'#071009', inputColor:'#071009',
    borderColor:'#4ac576', borderOpacity:.85, borderWidth:1, shadowStrength:0 } },
  { name:'Retro 15 KB', description:'Paleta âmbar de computador antigo', patch:{
    navigationPlacement:'left', controlsPlacement:'center', windowPresentation:'filled', surfaceStyle:'terminal',
    backgroundType:'color', backgroundColor:'#1c1609', panelColor:'#281d0d', panelOpacity:1, panelBlur:0,
    sidebarColor:'#281d0d', titlebarColor:'#281d0d',
    cardColor:'#31240f', cardOpacity:1, cardBorderColor:'#dba747', cardBorderOpacity:.65, cardRadius:0, cardPadding:18, cardGap:16,
    panelRadius:0, buttonRadius:0, windowRadius:0, fontFamily:'mono', primaryColor:'#ffc45a', primaryHover:'#ffdb94',
    textColor:'#ffe5b2', secondaryTextColor:'#c7a76f', buttonTextColor:'#241905', inputColor:'#170f05',
    borderColor:'#dba747', borderOpacity:.8, borderWidth:1, shadowStrength:0 } },
];
export const SKIN_PALETTES = [
  { name:'Violeta', primaryColor:'#9966ff', primaryHover:'#b799ff', backgroundColor:'#10101b', panelColor:'#191627', textColor:'#f5f2ff', secondaryTextColor:'#b8b1cd', inputColor:'#11101c', buttonTextColor:'#ffffff' },
  { name:'Oceano', primaryColor:'#087c92', primaryHover:'#096c80', backgroundColor:'#071b25', panelColor:'#102937', textColor:'#effaff', secondaryTextColor:'#a6c6d8', inputColor:'#091e2a', buttonTextColor:'#ffffff' },
  { name:'Floresta', primaryColor:'#207c5e', primaryHover:'#19674d', backgroundColor:'#0d1914', panelColor:'#172d23', textColor:'#edf8f0', secondaryTextColor:'#b1cabc', inputColor:'#0d2018', buttonTextColor:'#ffffff' },
  { name:'Claro', primaryColor:'#6546c4', primaryHover:'#5435b4', backgroundColor:'#e9edf5', panelColor:'#f7f8fc', textColor:'#222737', secondaryTextColor:'#525d76', inputColor:'#ffffff', buttonTextColor:'#ffffff' },
];
