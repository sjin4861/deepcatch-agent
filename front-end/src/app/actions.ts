'use server';

import { summarizeCallInformation as summarizeCallInformationFlow } from "@/ai/flows/summarize-call-information";
import { z } from "zod";

const summarizeSchema = z.object({
    transcript: z.string(),
});

export async function getSummary(formData: FormData) {
    const validatedFields = summarizeSchema.safeParse({
        transcript: formData.get('transcript'),
    });

    if (!validatedFields.success) {
        return {
            error: 'Invalid transcript provided.',
            summary: null,
        };
    }

    try {
        const result = await summarizeCallInformationFlow({
            callTranscript: validatedFields.data.transcript,
        });
        return { summary: result.summary, error: null };
    } catch (error) {
        console.error(error);
        return {
            error: 'Failed to generate summary. Please try again.',
            summary: null,
        };
    }
}
