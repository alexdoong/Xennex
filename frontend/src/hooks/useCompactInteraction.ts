import { useEffect, useRef } from 'react';

/** One owner for native interaction state, including portaled skin controls. */
export function useCompactInteraction(enabled: boolean, view: string) {
  const api = useRef(window.chrome?.webview?.hostObjects?.api).current;
  useEffect(() => {
    if (!enabled || !api) return;
    let pointer = false, sent = false, disposed = false;
    const inside = (node: EventTarget | null) =>
      node instanceof Element && !!node.closest('.compact-panel, .skin-dock, .skin-dock-reopen');
    const publish = (value: boolean) => {
      if (value === sent) return;
      sent = value;
      // WebView2 returns a COM thenable; normalize before using Promise.catch.
      void Promise.resolve(api.SetCompactInteracting(value)).catch(error => console.error('[Compact] Interação:', error));
    };
    const update = () => {
      if (disposed) return;
      const el = document.activeElement;
      const editing = inside(el) && el instanceof Element &&
        el.matches('input, textarea, select, [contenteditable="true"]');
      publish(document.hasFocus() && (pointer || editing));
    };
    const down = (event: PointerEvent) => { pointer = inside(event.target); update(); };
    const up = () => { pointer = false; update(); };
    const blur = () => { pointer = false; publish(false); };
    const focus = () => queueMicrotask(update);
    document.addEventListener('pointerdown', down, true);
    document.addEventListener('pointerup', up, true);
    document.addEventListener('pointercancel', up, true);
    document.addEventListener('focusin', focus);
    document.addEventListener('focusout', focus);
    window.addEventListener('blur', blur);
    update();
    return () => {
      disposed = true;
      document.removeEventListener('pointerdown', down, true);
      document.removeEventListener('pointerup', up, true);
      document.removeEventListener('pointercancel', up, true);
      document.removeEventListener('focusin', focus);
      document.removeEventListener('focusout', focus);
      window.removeEventListener('blur', blur);
      publish(false);
    };
  }, [api, enabled, view]);
}
