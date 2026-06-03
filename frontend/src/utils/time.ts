const OFFSET_SUFFIX_RE = /(Z|[+-]\d{2}:\d{2})$/i;
const SQLITE_UTC_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

function normalizeApiDateString(value: string): string {
  let normalized = value.trim();
  if (SQLITE_UTC_RE.test(normalized)) {
    normalized = normalized.replace(' ', 'T');
  }
  if (!OFFSET_SUFFIX_RE.test(normalized)) {
    normalized = `${normalized}Z`;
  }
  return normalized;
}

export function parseApiDate(value?: string | null): Date | null {
  if (!value) return null;
  const normalized = normalizeApiDateString(value);
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatRelativeApiTime(value?: string | null): string {
  const parsed = parseApiDate(value);
  if (!parsed) return 'Just now';
  const diff = Date.now() - parsed.getTime();
  const mins = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

export function formatApiDateTime(
  value?: string | null,
  options: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  },
): string {
  const parsed = parseApiDate(value);
  if (!parsed) return 'Not yet';
  return parsed.toLocaleString('en-US', options);
}

export function formatApiDate(
  value?: string | null,
  options: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  },
): string {
  const parsed = parseApiDate(value);
  if (!parsed) return 'Not yet';
  return parsed.toLocaleDateString('en-US', options);
}

export function formatHHMM(value?: string | null): string {
  const parsed = parseApiDate(value);
  if (!parsed) return '--:--';
  return parsed.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

export function compareApiDatesDesc(left?: string | null, right?: string | null): number {
  const leftTs = parseApiDate(left)?.getTime() ?? 0;
  const rightTs = parseApiDate(right)?.getTime() ?? 0;
  return rightTs - leftTs;
}

export function compareApiDatesAsc(left?: string | null, right?: string | null): number {
  const leftTs = parseApiDate(left)?.getTime() ?? 0;
  const rightTs = parseApiDate(right)?.getTime() ?? 0;
  return leftTs - rightTs;
}

export function isApiDateAfter(left?: string | null, right?: string | null): boolean {
  const leftTs = parseApiDate(left)?.getTime();
  const rightTs = parseApiDate(right)?.getTime();
  if (leftTs == null || rightTs == null) return false;
  return leftTs > rightTs;
}
