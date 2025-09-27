import type { TranslationKey } from '@/locale/messages';

type TranslateFn = (key: TranslationKey, values?: Record<string, string | number | null | undefined>) => string;

const STATUS_KEY_MAP: Record<string, TranslationKey> = {
    queued: 'transcription.status.queued',
    initiated: 'transcription.status.initiated',
    ringing: 'transcription.status.ringing',
    'in-progress': 'transcription.status.in-progress',
    inprogress: 'transcription.status.in-progress',
    answered: 'transcription.status.answered',
    completed: 'transcription.status.completed',
    busy: 'transcription.status.busy',
    failed: 'transcription.status.failed',
    'no-answer': 'transcription.status.no-answer',
    noanswer: 'transcription.status.no-answer',
    canceled: 'transcription.status.canceled',
    cancelled: 'transcription.status.canceled',
};

export function localizeCallStatus(status: string | null | undefined, t: TranslateFn): string {
    if (!status || status.trim().length === 0) {
        return t('transcription.status.unknown');
    }
    const normalized = status.trim().toLowerCase().replace(/_/g, '-');
    const key = STATUS_KEY_MAP[normalized];
    if (!key) {
        return status;
    }
    return t(key);
}
