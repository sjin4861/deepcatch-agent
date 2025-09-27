# Deepcatch Agent Frontend

Next.js dashboard for the 낚시 예약 AI 에이전트. The UI surfaces chat with the agent, live tool insights, and now a Kakao map preview for the generated route.

## Quick start

```bash
pnpm install
pnpm dev
```

By default the app expects the FastAPI backend at `http://localhost:8000`. Adjust `NEXT_PUBLIC_API_BASE_URL` if needed.

## Environment variables

Create a `.env.local` (or set variables in your hosting provider) with:

```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_KAKAO_MAP_KEY=your_kakao_javascript_key
```

- `NEXT_PUBLIC_KAKAO_MAP_KEY` is required to render the driving route and business pins on Kakao Maps.

## Key files

- `src/components/dashboard/chatbot.tsx` – conversational UI with inline call suggestions.
- `src/components/dashboard/information-summary.tsx` – aggregates agent tool outputs, including the Kakao map preview.
- `src/components/dashboard/map-route-preview.tsx` – Kakao map renderer fed by the new `map_route_generation_api` tool metadata.
