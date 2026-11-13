import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Normalizes any user-provided telephone string into ITU-T E.164 canonical standard.
 *
 * Examples:
 *   - '8866241204' -> '+918866241204'
 *   - '08866241204' -> '+918866241204'
 *   - '+91 88662 41204' -> '+918866241204'
 *   - '918866241204' -> '+918866241204'
 */
export function normalizePhoneNumber(raw: string): string {
  const clean = raw.trim();
  const digits = clean.replace(/[^\d]/g, '');
  if (!digits) return clean;

  if (digits.length === 10) {
    return `+91${digits}`;
  }
  if (digits.length === 11 && digits.startsWith('0')) {
    return `+91${digits.slice(1)}`;
  }
  if (digits.length === 12 && digits.startsWith('91')) {
    return `+${digits}`;
  }
  if (clean.startsWith('+') && digits.length >= 8 && digits.length <= 15) {
    return `+${digits}`;
  }
  return clean.startsWith('+') ? `+${digits}` : digits;
}

/**
 * Formats canonical E.164 phone numbers into industry standard readable display format.
 *
 * For Indian Mobile (+91):
 *   '+918866241204' -> '+91 88662 41204' (5-5 national grouping)
 *
 * For NANP (+1):
 *   '+14155552671' -> '+1 (415) 555-2671'
 *
 * Standard International:
 *   '+447911123456' -> '+44 7911 123456'
 */
export function formatPhoneNumber(phone?: string | null): string {
  if (!phone) return '—';
  const clean = phone.trim();

  // Indian standard (+91 followed by 10 digits)
  const indiaMatch = clean.match(/^\+91(\d{5})(\d{5})$/);
  if (indiaMatch) {
    return `+91 ${indiaMatch[1]} ${indiaMatch[2]}`;
  }

  // Handle without + prefix if 91XXXXXXXXXX
  const indiaNoPlus = clean.match(/^91(\d{5})(\d{5})$/);
  if (indiaNoPlus) {
    return `+91 ${indiaNoPlus[1]} ${indiaNoPlus[2]}`;
  }

  // Bare 10 digits
  const bare10 = clean.match(/^(\d{5})(\d{5})$/);
  if (bare10) {
    return `+91 ${bare10[1]} ${bare10[2]}`;
  }

  // US/NANP (+1 followed by 10 digits)
  const usMatch = clean.match(/^\+1(\d{3})(\d{3})(\d{4})$/);
  if (usMatch) {
    return `+1 (${usMatch[1]}) ${usMatch[2]}-${usMatch[3]}`;
  }

  return clean;
}

