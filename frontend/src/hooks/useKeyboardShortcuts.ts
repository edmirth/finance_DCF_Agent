import { useEffect, useRef } from 'react';
import { KeyboardShortcuts } from '../utils/accessibility';

interface ShortcutConfig {
  key: string;
  modifier?: 'ctrl' | 'meta' | 'ctrlOrMeta';
  callback: () => void;
  description?: string;
}

/**
 * Hook to register keyboard shortcuts
 * Automatically cleans up on unmount
 */
export function useKeyboardShortcuts(shortcuts: ShortcutConfig[]): void {
  const managerRef = useRef<KeyboardShortcuts | null>(null);

  useEffect(() => {
    // Create manager if it doesn't exist
    if (!managerRef.current) {
      managerRef.current = new KeyboardShortcuts();
      managerRef.current.startListening();
    }

    const manager = managerRef.current;

    // Register all shortcuts
    shortcuts.forEach(({ key, modifier, callback }) => {
      manager.register(key, callback, modifier);
    });

    // Cleanup function
    return () => {
      shortcuts.forEach(({ key, modifier }) => {
        manager.unregister(key, modifier);
      });
    };
  }, [shortcuts]);

  // Cleanup manager on unmount
  useEffect(() => {
    return () => {
      if (managerRef.current) {
        managerRef.current.destroy();
        managerRef.current = null;
      }
    };
  }, []);
}

/**
 * Hook to announce messages to screen readers
 */
export function useScreenReaderAnnouncement() {
  return (message: string, priority: 'polite' | 'assertive' = 'polite') => {
    const announcement = document.createElement('div');
    announcement.setAttribute('role', priority === 'assertive' ? 'alert' : 'status');
    announcement.setAttribute('aria-live', priority);
    announcement.setAttribute('aria-atomic', 'true');
    announcement.className = 'sr-only';
    announcement.textContent = message;

    document.body.appendChild(announcement);

    setTimeout(() => {
      if (announcement.parentNode) {
        document.body.removeChild(announcement);
      }
    }, 1000);
  };
}
