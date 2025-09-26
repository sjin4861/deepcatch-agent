export type ToolResult = {
    id: string;
    toolName?: string;
    title?: string;
    content: string;
    metadata?: Record<string, unknown> | null;
    receivedAt: string;
};

export type ToolResultPayload = {
    id?: string;
    toolName?: string;
    title?: string;
    content?: string;
    text?: string;
    output?: string;
    metadata?: Record<string, unknown> | null;
    createdAt?: string;
};

export type AgentChatResponse = {
    message: string;
    toolResults?: ToolResultPayload[];
    callSuggested?: boolean;
};
