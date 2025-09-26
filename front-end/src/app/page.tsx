import Header from '@/components/dashboard/header';
import RealtimeTranscription from '@/components/dashboard/realtime-transcription';
import Chatbot from '@/components/dashboard/chatbot';
import InformationSummary from '@/components/dashboard/information-summary';
import FishingYieldChart from '@/components/dashboard/fishing-yield-chart';

export default function Home() {
  const fullTranscript = `Agent: Thank you for calling Aqua Adventures, this is Sarah speaking. How can I help you today?
Caller: Hi Sarah, I'm interested in booking a fishing trip. I saw on your website you have trips in the Florida Keys.
Agent: Yes, we do! The Florida Keys are fantastic for fishing this time of year. We have a few options. Are you interested in deep-sea fishing or flats fishing?
Caller: I've always wanted to try deep-sea fishing. What kind of fish are you catching there right now?
Agent: Great choice! Right now, the Mahi-mahi and Wahoo are biting like crazy. Our charters have had a lot of success in the last few weeks. We offer half-day and full-day charters.
Caller: A full day sounds perfect. What's the cost for a full-day charter? And what does it include?
Agent: A full-day deep-sea charter is $1200 for up to 4 people. That includes the boat, captain, all the fishing gear, bait, and licenses. We also include a cooler with water and sodas. You just need to bring any snacks you'd like and of course, sunscreen!
Caller: That sounds reasonable. I'd like to book a trip for next Saturday.
Agent: Excellent! I can book that for you right now. Can I get your full name and a contact number?
Caller: My name is John Doe, and my number is 555-123-4567.
Agent: Perfect, John. You are all set for a full-day deep-sea fishing charter next Saturday. You'll receive a confirmation email shortly with all the details. We look forward to seeing you!
Caller: Thanks, Sarah! I'm excited.
Agent: You're welcome! Have a great day.`;

  return (
    <div className="flex flex-col min-h-screen bg-background">
      <Header />
      <main className="flex-1 p-4 sm:p-6 md:p-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
          <div className="lg:col-span-2 flex flex-col gap-6">
            <Chatbot />
          </div>
          <div className="lg:col-span-1 flex flex-col gap-6 h-[calc(100vh-10rem)]">
            <div className="flex flex-col h-1/2">
                <InformationSummary transcript={fullTranscript} />
            </div>
            <div className="flex flex-col h-1/2">
                <RealtimeTranscription transcript={fullTranscript} />
            </div>
            <FishingYieldChart />
          </div>
        </div>
      </main>
    </div>
  );
}
