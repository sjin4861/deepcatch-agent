'use client';

import { useState, useTransition } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TextSearch, Loader2 } from 'lucide-react';
import { getSummary } from '@/app/actions';
import { useToast } from "@/hooks/use-toast";

type InfoSummaryProps = {
  transcript: string;
};

export default function InformationSummary({ transcript }: InfoSummaryProps) {
  const { toast } = useToast();
  const [summary, setSummary] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSummarize = () => {
    const formData = new FormData();
    formData.append('transcript', transcript);

    startTransition(async () => {
      const result = await getSummary(formData);
      if (result.error) {
          toast({
              variant: "destructive",
              title: "Error",
              description: result.error,
          });
      } else {
          setSummary(result.summary);
      }
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TextSearch className="text-accent" />
          Quick Information
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {summary ? (
          <div className="p-4 bg-secondary rounded-md text-sm text-secondary-foreground space-y-2 max-h-60 overflow-y-auto">
              <h3 className="font-semibold">Call Summary:</h3>
              <p className="whitespace-pre-wrap">{summary}</p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Click the button to generate a summary of the conversation.
          </p>
        )}

        <Button onClick={handleSummarize} disabled={isPending || !transcript} className="w-full">
          {isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Generating...
            </>
          ) : (
            'Generate Summary'
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
