import { describe, expect, it } from 'vitest';
import { DEFAULT_DISPLAY_TIMEZONE, formatDateTime, formatTime } from './format';

// The API guarantees every timestamp is a tz-aware UTC ISO-8601 string (see
// backend app.db.types.UTCDateTime) -- these fixtures use the "+00:00" shape
// Pydantic actually emits for an aware UTC datetime. formatTime/formatDateTime
// must convert that through a real IANA zone (Asia/Kolkata by default),
// never by adding a fixed 5.5-hour offset, and the assertions below don't
// depend on the machine running the test being in any particular zone --
// Intl's explicit `timeZone` option makes that irrelevant.

describe('DEFAULT_DISPLAY_TIMEZONE', () => {
  it('defaults to Asia/Kolkata for the demo', () => {
    expect(DEFAULT_DISPLAY_TIMEZONE).toBe('Asia/Kolkata');
  });
});

describe('formatTime', () => {
  it('converts a UTC instant to IST wall-clock time, exactly +05:30', () => {
    expect(formatTime('2026-09-04T14:53:43+00:00')).toBe('20:23:43');
  });

  it('accepts the "Z" suffix shape too', () => {
    expect(formatTime('2026-09-04T14:53:43Z')).toBe('20:23:43');
  });

  it('reproduces the reported bug scenario: 14:53 UTC displays as 20:23 IST, not 14:53', () => {
    const result = formatTime('2026-09-04T14:53:43Z');
    expect(result).not.toBe('14:53:43');
    expect(result).toBe('20:23:43');
  });

  it('rolls the display over at the exact UTC instant IST crosses midnight', () => {
    expect(formatTime('2026-01-15T18:29:00Z')).toBe('23:59:00');
    expect(formatTime('2026-01-15T18:30:00Z')).toBe('00:00:00');
    expect(formatTime('2026-01-15T18:31:00Z')).toBe('00:01:00');
  });

  it('honors an explicit timeZone override (client-configurable display timezone)', () => {
    expect(formatTime('2026-01-15T10:00:00Z', 'Asia/Tokyo')).toBe('19:00:00');
  });

  it('passes through null/undefined/empty as a placeholder, not a crash', () => {
    expect(formatTime(null)).toBe('—');
    expect(formatTime(undefined)).toBe('—');
    expect(formatTime('')).toBe('—');
  });
});

describe('formatDateTime', () => {
  it('shows the IST calendar date rolling to the next day at the boundary', () => {
    const beforeMidnightIst = formatDateTime('2026-01-15T18:29:00Z');
    const afterMidnightIst = formatDateTime('2026-01-15T18:30:00Z');
    expect(beforeMidnightIst).toContain('15 Jan 2026');
    expect(afterMidnightIst).toContain('16 Jan 2026');
  });

  it('carries a year-end boundary across both the date and the year', () => {
    expect(formatDateTime('2025-12-31T19:00:00Z')).toContain('01 Jan 2026');
  });
});
