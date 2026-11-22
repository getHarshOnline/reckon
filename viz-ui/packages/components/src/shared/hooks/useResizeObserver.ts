import { useState, useEffect, type RefObject } from 'react';

interface Size {
  width: number;
  height: number;
}

/**
 * Hook that observes element size changes using ResizeObserver.
 *
 * @param ref - React ref to the element to observe
 * @returns Current size of the element
 *
 * @example
 * ```tsx
 * const ref = useRef<HTMLDivElement>(null);
 * const size = useResizeObserver(ref);
 * console.log(size.width, size.height);
 * ```
 */
export function useResizeObserver<T extends HTMLElement>(
  ref: RefObject<T>
): Size {
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        setSize({ width, height });
      }
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return size;
}

export default useResizeObserver;
