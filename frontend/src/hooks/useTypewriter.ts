import { useState, useEffect, useRef } from 'react';

interface UseTypewriterOptions {
  /** Speed in milliseconds per character (lower = faster) */
  speed?: number;
  /** Whether to enable the typewriter effect */
  enabled?: boolean;
  /** Callback when typing is complete */
  onComplete?: () => void;
}

/**
 * useTypewriter - Hook for creating a typewriter animation effect
 * 
 * @param text - The full text to type out
 * @param options - Configuration options
 * @returns The currently displayed text (progressively revealed)
 * 
 * @example
 * const displayedText = useTypewriter("Hello, world!", { speed: 30 });
 */
export function useTypewriter(
  text: string,
  options: UseTypewriterOptions = {}
): string {
  const { speed = 20, enabled = true, onComplete } = options;
  const [displayed, setDisplayed] = useState('');
  const previousTextRef = useRef('');
  const completedRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setDisplayed(text);
      return;
    }

    // If the new text is an extension of the previous text (streaming),
    // continue from where we left off
    if (text.startsWith(previousTextRef.current)) {
      // Text was extended, keep our current position
    } else {
      // Text changed completely, reset
      setDisplayed('');
      completedRef.current = false;
    }

    previousTextRef.current = text;

    if (displayed.length >= text.length) {
      if (!completedRef.current && onComplete) {
        completedRef.current = true;
        onComplete();
      }
      return;
    }

    const timer = setTimeout(() => {
      setDisplayed(text.slice(0, displayed.length + 1));
    }, speed);

    return () => clearTimeout(timer);
  }, [text, displayed, speed, enabled, onComplete]);

  // Reset completion flag when text changes
  useEffect(() => {
    completedRef.current = false;
  }, [text]);

  return enabled ? displayed : text;
}

/**
 * useStreamingText - Hook optimized for streaming text (no animation delay)
 * 
 * When text is actively streaming (growing), shows it immediately.
 * When text is complete, can optionally apply a final animation.
 * 
 * @param text - The streaming text
 * @param isStreaming - Whether the text is currently streaming
 */
export function useStreamingText(
  text: string,
  isStreaming: boolean
): string {
  const [displayed, setDisplayed] = useState('');
  const previousLengthRef = useRef(0);

  useEffect(() => {
    if (isStreaming) {
      // While streaming, show text immediately (no delay)
      setDisplayed(text);
      previousLengthRef.current = text.length;
    } else if (text.length > previousLengthRef.current) {
      // Streaming just stopped, show full text
      setDisplayed(text);
      previousLengthRef.current = text.length;
    }
  }, [text, isStreaming]);

  return displayed;
}

export default useTypewriter;
