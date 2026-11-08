export const noteStatus:Record<string,string>={proposed:'Proposta',hypothesis:'Hipótese',confirmed:'Confirmada por você',superseded:'Superada'};
export function downloadText(name:string,text:string,type='text/markdown') {
  const url=URL.createObjectURL(new Blob([text],{type}));
  const link=document.createElement('a');link.href=url;link.download=name;link.click();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}
