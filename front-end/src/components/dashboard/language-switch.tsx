'use client';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useLocale } from '@/context/locale-context';
import { supportedLocales } from '@/locale/messages';

export default function LanguageSwitch() {
    const { locale, setLocale } = useLocale();

    return (
        <Select value={locale} onValueChange={value => setLocale(value as typeof locale)}>
            <SelectTrigger className="w-[140px] bg-background">
                <SelectValue />
            </SelectTrigger>
            <SelectContent>
                {supportedLocales.map(item => (
                    <SelectItem key={item.value} value={item.value}>
                        <span className="flex items-center gap-2">
                            {item.flag && <span>{item.flag}</span>}
                            <span>{item.label}</span>
                        </span>
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}
