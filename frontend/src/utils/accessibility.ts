/**
 * Accessibility utilities for screen readers and keyboard navigation
 */

/**
 * Announce message to screen readers
 * Uses aria-live region pattern
 */
export function announceToScreenReader(message: string, priority: 'polite' | 'assertive' = 'polite'): void {
  const announcement = document.createElement('div');
  announcement.setAttribute('role', priority === 'assertive' ? 'alert' : 'status');
  announcement.setAttribute('aria-live', priority);
  announcement.setAttribute('aria-atomic', 'true');
  announcement.className = 'sr-only';
  announcement.textContent = message;

  document.body.appendChild(announcement);

  // Remove after announcement is made
  setTimeout(() => {
    document.body.removeChild(announcement);
  }, 1000);
}

/**
 * Get descriptive text for rating
 */
export function getRatingDescription(rating: string): string {
  const lower = rating.toLowerCase();
  if (lower.includes('buy') || lower.includes('strong buy')) {
    return 'Positive investment rating: Buy';
  } else if (lower.includes('sell') || lower.includes('strong sell')) {
    return 'Negative investment rating: Sell';
  } else if (lower.includes('hold')) {
    return 'Neutral investment rating: Hold';
  }
  return `Investment rating: ${rating}`;
}

/**
 * Get descriptive text for surprise result
 */
export function getSurpriseDescription(
  quarter: string,
  beat: boolean,
  surprisePercent: number
): string {
  const direction = beat ? 'beat' : 'missed';
  const by = Math.abs(surprisePercent).toFixed(2);
  return `${quarter} earnings ${direction} expectations by ${by} percent`;
}

/**
 * Get descriptive text for trend
 */
export function getTrendDescription(
  metric: string,
  value: number,
  change: number,
  changePercent: number
): string {
  const direction = change >= 0 ? 'increased' : 'decreased';
  const by = Math.abs(changePercent).toFixed(2);
  return `${metric} is ${value.toLocaleString()}, ${direction} by ${by} percent`;
}

/**
 * Format currency for screen readers
 */
export function formatCurrencyForScreenReader(value: number): string {
  if (value >= 1000000000) {
    return `${(value / 1000000000).toFixed(2)} billion dollars`;
  } else if (value >= 1000000) {
    return `${(value / 1000000).toFixed(2)} million dollars`;
  } else if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} thousand dollars`;
  } else {
    return `${value.toFixed(2)} dollars`;
  }
}

/**
 * Trap focus within a container (for modals)
 */
export function trapFocus(container: HTMLElement): () => void {
  const focusableElements = container.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return;

    if (e.shiftKey) {
      // Shift + Tab
      if (document.activeElement === firstElement) {
        e.preventDefault();
        lastElement?.focus();
      }
    } else {
      // Tab
      if (document.activeElement === lastElement) {
        e.preventDefault();
        firstElement?.focus();
      }
    }
  };

  container.addEventListener('keydown', handleKeyDown);

  // Return cleanup function
  return () => {
    container.removeEventListener('keydown', handleKeyDown);
  };
}

/**
 * Global keyboard shortcuts manager
 */
export class KeyboardShortcuts {
  private shortcuts: Map<string, () => void> = new Map();
  private isListening = false;

  register(key: string, callback: () => void, modifier?: 'ctrl' | 'meta' | 'ctrlOrMeta'): void {
    const shortcutKey = modifier ? `${modifier}+${key}` : key;
    this.shortcuts.set(shortcutKey, callback);
  }

  unregister(key: string, modifier?: 'ctrl' | 'meta' | 'ctrlOrMeta'): void {
    const shortcutKey = modifier ? `${modifier}+${key}` : key;
    this.shortcuts.delete(shortcutKey);
  }

  private handleKeyDown = (e: KeyboardEvent): void => {
    let shortcutKey = e.key.toLowerCase();

    if (e.ctrlKey && e.metaKey) {
      // Both modifiers (unlikely but handle it)
      shortcutKey = `ctrlOrMeta+${shortcutKey}`;
    } else if (e.ctrlKey) {
      shortcutKey = `ctrl+${shortcutKey}`;
    } else if (e.metaKey) {
      shortcutKey = `meta+${shortcutKey}`;
    }

    // Check for ctrlOrMeta pattern
    if ((e.ctrlKey || e.metaKey) && !shortcutKey.startsWith('ctrl+') && !shortcutKey.startsWith('meta+')) {
      const plainKey = shortcutKey.replace(/^(ctrl|meta)\+/, '');
      const ctrlOrMetaKey = `ctrlOrMeta+${plainKey}`;
      const callback = this.shortcuts.get(ctrlOrMetaKey);
      if (callback) {
        e.preventDefault();
        callback();
        return;
      }
    }

    const callback = this.shortcuts.get(shortcutKey);
    if (callback) {
      e.preventDefault();
      callback();
    }
  };

  startListening(): void {
    if (this.isListening) return;
    document.addEventListener('keydown', this.handleKeyDown);
    this.isListening = true;
  }

  stopListening(): void {
    if (!this.isListening) return;
    document.removeEventListener('keydown', this.handleKeyDown);
    this.isListening = false;
  }

  destroy(): void {
    this.stopListening();
    this.shortcuts.clear();
  }
}
