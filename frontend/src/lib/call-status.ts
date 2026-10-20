/**
 * Canonical Call Status Utilities & Presentation Helpers.
 *
 * Provides unified status labels, badge variants, and filter definitions
 * across Live Telemetry and Call Transcripts mission control views.
 */

export const CALL_STATUS_LABELS: Record<string, string> = {
  completed: 'Answered',
  in_progress: 'In Progress',
  ringing: 'Ringing',
  failed: 'Failed',
  busy: 'Busy',
  no_answer: 'No Answer',
  cancelled: 'Cancelled',
  pending: 'Queued',
};

export const CALL_STATUS_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'completed', label: 'Answered' },
  { id: 'failed', label: 'Failed' },
  { id: 'active', label: 'Ongoing' },
] as const;

export function getCallStatusLabel(status: string): string {
  if (!status) return 'Unknown';
  return CALL_STATUS_LABELS[status.toLowerCase()] ?? status;
}

export function getCallStatusBadgeVariant(status: string): 'live' | 'ringing' | 'destructive' | 'secondary' | 'amber' {
  switch (status.toLowerCase()) {
    case 'completed':
      return 'live';
    case 'in_progress':
      return 'live';
    case 'ringing':
      return 'ringing';
    case 'failed':
    case 'busy':
      return 'destructive';
    case 'no_answer':
    case 'cancelled':
      return 'amber';
    case 'pending':
    default:
      return 'secondary';
  }
}
