const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

/** Amounts arrive as decimal strings so no precision is lost in transit;
 *  they are only turned into a Number at the point of display. */
export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return INR.format(numeric);
}

/** Every timestamp the API returns is UTC (see backend app.db.types --
 *  a tz-aware ISO-8601 string, e.g. "...+00:00"). This is the one place
 *  those get converted to a wall-clock display time, and it always goes
 *  through a real IANA zone via Intl -- never fixed +05:30 arithmetic -- so
 *  DST and any future rule change are handled for free. Matches
 *  app.core.timezone.DEFAULT_DISPLAY_TIMEZONE on the backend. */
export const DEFAULT_DISPLAY_TIMEZONE = 'Asia/Kolkata';

const timeFormatters = new Map<string, Intl.DateTimeFormat>();
const dateTimeFormatters = new Map<string, Intl.DateTimeFormat>();

function cachedFormatter(
  cache: Map<string, Intl.DateTimeFormat>,
  timeZone: string,
  options: Intl.DateTimeFormatOptions,
): Intl.DateTimeFormat {
  let formatter = cache.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-GB', { ...options, timeZone });
    cache.set(timeZone, formatter);
  }
  return formatter;
}

/** A client's own display timezone (Client.display_timezone) should be
 *  passed as `timeZone` wherever a client is in scope; the constant above is
 *  only the fallback for call sites with no client context. */
export function formatTime(
  value: string | null | undefined,
  timeZone: string = DEFAULT_DISPLAY_TIMEZONE,
): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return cachedFormatter(timeFormatters, timeZone, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatDateTime(
  value: string | null | undefined,
  timeZone: string = DEFAULT_DISPLAY_TIMEZONE,
): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return cachedFormatter(dateTimeFormatters, timeZone, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatPercent(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(digits).replace(/\.?0+$/, '')}%`;
}
