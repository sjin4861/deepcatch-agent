'use server';
/**
 * @fileOverview Summarizes key information from a call transcript.
 *
 * - summarizeCallInformation - A function that summarizes a call transcript.
 * - SummarizeCallInformationInput - The input type for the summarizeCallInformation function.
 * - SummarizeCallInformationOutput - The return type for the summarizeCallInformation function.
 */

import {ai} from '@/ai/genkit';
import {z} from 'genkit';

const SummarizeCallInformationInputSchema = z.object({
  callTranscript: z
    .string()
    .describe('The transcript of the call to summarize.'),
});
export type SummarizeCallInformationInput = z.infer<
  typeof SummarizeCallInformationInputSchema
>;

const SummarizeCallInformationOutputSchema = z.object({
  summary: z.string().describe('A concise summary of the call transcript.'),
});
export type SummarizeCallInformationOutput = z.infer<
  typeof SummarizeCallInformationOutputSchema
>;

export async function summarizeCallInformation(
  input: SummarizeCallInformationInput
): Promise<SummarizeCallInformationOutput> {
  return summarizeCallInformationFlow(input);
}

const prompt = ai.definePrompt({
  name: 'summarizeCallInformationPrompt',
  input: {schema: SummarizeCallInformationInputSchema},
  output: {schema: SummarizeCallInformationOutputSchema},
  prompt: `You are an expert summarizer of call transcripts.  Please provide a concise summary of the key information discussed in the following call transcript:

Transcript:
{{callTranscript}}`,
});

const summarizeCallInformationFlow = ai.defineFlow(
  {
    name: 'summarizeCallInformationFlow',
    inputSchema: SummarizeCallInformationInputSchema,
    outputSchema: SummarizeCallInformationOutputSchema,
  },
  async input => {
    const {output} = await prompt(input);
    return output!;
  }
);
