"use client";

import { Fish } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useLocale } from '@/context/locale-context';
import LanguageSwitch from './language-switch';

export default function Header() {
    const { t } = useLocale();

    return (
        <header className="flex items-center justify-between p-4 border-b bg-card shadow-sm">
            <div className="flex items-center gap-3">
                <Fish className="w-8 h-8 text-primary" />
                <h1 className="text-2xl font-bold text-foreground font-headline">{t('header.title')}</h1>
            </div>
            <div className="flex items-center gap-4">
                <div className="hidden md:flex flex-col items-end text-[11px] text-muted-foreground">
                    <span>{t('header.languageLabel')}</span>
                </div>
                <LanguageSwitch />
                <Avatar>
                    <AvatarImage src="https://picsum.photos/seed/123/40/40" data-ai-hint="person face" />
                    <AvatarFallback>AG</AvatarFallback>
                </Avatar>
            </div>
        </header>
    );
}
