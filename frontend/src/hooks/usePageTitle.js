import { useEffect } from "react";

/**
 * Set a unique document title for the current view (WCAG 2.4.2).
 */
export default function usePageTitle(title) {
  useEffect(() => {
    if (!title) return undefined;
    const previous = document.title;
    document.title = `${title} — DFAT`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
