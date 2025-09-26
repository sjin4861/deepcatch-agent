# **App Name**: Call Canvas

## Core Features:

- Chatbot UI: Implements a chatbot interface using Next.js and TailwindCSS for smooth user interaction.
- Call Monitoring Dashboard: Displays real-time call monitoring information, allowing agents to track and manage conversations effectively.
- Quick Information Tool: Generates a summary of key information tool, extracted from the conversation using fishing API to allow fishing trips in appropriate regions. Uses LLM reasoning to decide when/if to incorporate these details.
- API State Management: Manages API states using React Query or SWR for efficient data fetching and caching.
- Data Visualization: Visualizes data, such as fishing yields, using Recharts for clear and insightful representation.
- Real-time Call Transcription: Provides real-time transcription of the ongoing calls, making it easy to review and analyze conversations. Updates to the display happen via websockets.
- Text Input: Implements a text input field with a send button to simulate conversations and test the Chatbot UI.

## Style Guidelines:

- Primary color: Deep blue (#2E5266) to convey trust and professionalism in the fishing trip management system.
- Background color: Light gray (#F0F4F7) for a clean and modern dashboard interface.
- Accent color: Teal (#4DB6AC) to highlight interactive elements and important data points, creating a balanced contrast.
- Body and headline font: 'Inter' (sans-serif) for clear and readable text in both the chatbot and dashboard.
- Use modern and minimalist icons from 'Simple Icons' to represent different data types and actions.
- Use a grid-based layout to organize dashboard components and ensure responsiveness across devices.
- Subtle animations and transitions to provide feedback and improve user experience.