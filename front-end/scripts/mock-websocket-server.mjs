import { WebSocketServer } from "ws";

const PORT = Number(process.env.MOCK_WS_PORT ?? 9003);

const TEMPLATE_TRANSCRIPTION = [
  {
    speaker: "Agent",
    text: "Thank you for calling Aqua Adventures, this is Sarah.",
  },
  {
    speaker: "Caller",
    text: "Hi Sarah, I'm looking to book a deep-sea fishing trip.",
  },
  {
    speaker: "Agent",
    text: "Great! The mahi-mahi bite has been fantastic. Are you thinking half or full day?",
  },
  {
    speaker: "Caller",
    text: "Let’s do a full-day trip. What does that include?",
  },
  {
    speaker: "Agent",
    text: "It’s $1,200 for up to four guests, captain, gear, bait, and licenses included.",
  },
  {
    speaker: "Caller",
    text: "Perfect. Could we schedule it for next Saturday?",
  },
  {
    speaker: "Agent",
    text: "Absolutely. May I have your name and callback number?",
  },
  { speaker: "Caller", text: "John Doe, 555-123-4567." },
  {
    speaker: "Agent",
    text: "Thanks, John. I’ll send the confirmation shortly.",
  },
];

const wss = new WebSocketServer({ port: PORT });
console.log(`Mock WebSocket server running on ws://localhost:${PORT}`);

wss.on("connection", (socket) => {
  console.log("Mock client connected");

  socket.send(JSON.stringify({ type: "status", status: "ready" }));

  let timer;
  let index = 0;

  const stopStream = () => {
    if (timer) {
      clearInterval(timer);
      timer = undefined;
    }
  };

  const streamSegments = () => {
    stopStream();
    index = 0;
    timer = setInterval(() => {
      if (index < TEMPLATE_TRANSCRIPTION.length) {
        const payload = {
          type: "transcription_segment",
          segment: TEMPLATE_TRANSCRIPTION[index],
          index,
          done: index === TEMPLATE_TRANSCRIPTION.length - 1,
        };
        socket.send(JSON.stringify(payload));
        index += 1;
      } else {
        socket.send(JSON.stringify({ type: "transcription_done" }));
        stopStream();
      }
    }, 1500);
  };

  socket.on("message", (data) => {
    try {
      const event = JSON.parse(data.toString());
      if (event.type === "start_call") {
        streamSegments();
      } else if (event.type === "stop_call") {
        stopStream();
        socket.send(JSON.stringify({ type: "status", status: "stopped" }));
      }
    } catch (error) {
      console.error("Failed to parse message", error);
    }
  });

  socket.on("close", () => {
    console.log("Mock client disconnected");
    stopStream();
  });
});
