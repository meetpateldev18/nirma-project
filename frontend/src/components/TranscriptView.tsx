/**
 * Unified Call Records & Transcripts View.
 *
 * Re-exports the unified LiveTelemetryView component to provide backward compatibility
 * across all existing lazy-loaded chunks and route consumers.
 */

import { LiveTelemetryView } from './LiveTelemetryView';

export { LiveTelemetryView };
export const TranscriptView = LiveTelemetryView;
export default TranscriptView;

export { ConversationalTranscript, type ConversationalTranscriptProps } from './ConversationalTranscript';
export { 
  CALL_STATUS_FILTERS, 
  getCallStatusLabel, 
  getCallStatusBadgeVariant 
} from '@/lib/call-status';
