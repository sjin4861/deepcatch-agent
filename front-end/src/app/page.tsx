import Header from '@/components/dashboard/header';
import RealtimeTranscription from '@/components/dashboard/realtime-transcription';
import Chatbot from '@/components/dashboard/chatbot';
import InformationSummary from '@/components/dashboard/information-summary';
import { TranscriptionProvider } from '@/context/transcription-context';
import { AgentInsightsProvider } from '@/context/agent-insights-context';

export default function Home() {
    return (
        <div className="flex flex-col min-h-screen bg-background">
            <Header />
            <main className="flex-1 p-4 sm:p-6 md:p-8">
                <AgentInsightsProvider>
                    <TranscriptionProvider>
                        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] h-full">
                            <section className="flex flex-col gap-6 min-h-0">
                                <Chatbot />
                            </section>
                            <aside className="flex flex-col gap-6 min-h-0">
                                <InformationSummary />
                                <RealtimeTranscription />
                            </aside>
                        </div>
                    </TranscriptionProvider>
                </AgentInsightsProvider>
            </main>
        </div>
    );
}
