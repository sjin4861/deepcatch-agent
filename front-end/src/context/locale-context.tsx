'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { defaultLocale, messages, supportedLocales } from '@/locale/messages';
import type { LocaleCode, TranslationKey } from '@/locale/messages';

type LocaleContextValue = {
    locale: LocaleCode;
    setLocale: (value: LocaleCode) => void;
    t: (key: TranslationKey, values?: Record<string, string | number | undefined | null>) => string;
    locales: typeof supportedLocales;
};

const STORAGE_KEY = 'deepcatch.locale';

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readBrowserLocale(): LocaleCode {
    if (typeof window === 'undefined') {
        return defaultLocale;
    }
    const stored = window.localStorage.getItem(STORAGE_KEY) as LocaleCode | null;
    if (stored && supportedLocales.some(item => item.value === stored)) {
        return stored;
    }
    const navigatorLocale = (window.navigator.language || '').toLowerCase();
    if (navigatorLocale.startsWith('ko')) return 'ko';
    if (navigatorLocale.startsWith('ja')) return 'ja';
    return 'en';
}

function interpolate(template: string, values?: Record<string, string | number | undefined | null>): string {
    if (!values) return template;
    return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, key: string) => {
        const value = values[key];
        if (value === undefined || value === null) {
            return '';
        }
        return String(value);
    });
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
    const [locale, setLocaleState] = useState<LocaleCode>(() => {
        try {
            return readBrowserLocale();
        } catch (err) {
            console.warn('Failed to read browser locale', err);
            return defaultLocale;
        }
    });

    useEffect(() => {
        if (typeof document !== 'undefined') {
            document.documentElement.lang = locale;
        }
    }, [locale]);

    const setLocale = useCallback((value: LocaleCode) => {
        setLocaleState(value);
        if (typeof window !== 'undefined') {
            window.localStorage.setItem(STORAGE_KEY, value);
        }
    }, []);

    const t = useCallback(
        (key: TranslationKey, values?: Record<string, string | number | undefined | null>) => {
            const table = messages[key];
            if (!table) {
                console.warn(`Missing translation key: ${key}`);
                return key;
            }
            const template = table[locale] ?? table[defaultLocale] ?? key;
            return interpolate(template, values);
        },
        [locale],
    );

    const value = useMemo<LocaleContextValue>(() => ({
        locale,
        setLocale,
        t,
        locales: supportedLocales,
    }), [locale, setLocale, t]);

    return (
        <LocaleContext.Provider value={value}>
            {children}
        </LocaleContext.Provider>
    );
}

export function useLocale(): LocaleContextValue {
    const context = useContext(LocaleContext);
    if (!context) {
        throw new Error('useLocale must be used within LocaleProvider');
    }
    return context;
}
