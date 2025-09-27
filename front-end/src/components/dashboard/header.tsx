import { Fish, Phone } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';

export default function Header() {
    return (
        <header className="flex items-center justify-between p-4 border-b bg-card shadow-sm">
            <div className="flex items-center gap-3">
                <Fish className="w-8 h-8 text-primary" />
                <h1 className="text-2xl font-bold text-foreground font-headline">낚시하러 오시구룡~</h1>
            </div>
            <div className="flex items-center gap-4">
                <Avatar>
                    <AvatarImage src="https://picsum.photos/seed/123/40/40" data-ai-hint="person face" />
                    <AvatarFallback>AG</AvatarFallback>
                </Avatar>
            </div>
        </header>
    );
}
