import { useEffect, useRef, useState } from 'react';

/** Keeps the bar visible while hovered and cancels pending work on unmount. */
export function useAutoHide(enabled: boolean, delay = 500) {
  const [hovered, setHovered] = useState(false);
  const timer = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const cancel = () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  };

  useEffect(() => cancel, []);

  return {
    visible: !enabled || hovered,
    onMouseEnter: () => {
      cancel();
      setHovered(true);
    },
    onMouseLeave: () => {
      cancel();
      timer.current = window.setTimeout(() => {
        timer.current = null;
        setHovered(false);
      }, delay);
    },
  };
}
