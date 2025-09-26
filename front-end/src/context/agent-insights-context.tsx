'use client';

import {
    createContext,
    type ReactNode,
    useCallback,
    useContext,
    useMemo,
    useState,
} from 'react';
import type { ToolResult } from '@/types/agent';

type AgentInsightsContextValue = {
    toolResults: ToolResult[];
    recordToolResults: (results: ToolResult[] | null | undefined) => void;
    clearToolResults: () => void;
};

const AgentInsightsContext = createContext<AgentInsightsContextValue | null>(null);

type ProviderProps = {
    children: ReactNode;
};

export function AgentInsightsProvider({ children }: ProviderProps) {
    const [toolResults, setToolResults] = useState<ToolResult[]>([]);

    const recordToolResults = useCallback((results: ToolResult[] | null | undefined) => {
        if (!results || results.length === 0) {
            return;
        }
        setToolResults(prev => {
            if (prev.length === 0) {
                return results.slice().sort(sortByReceivedAt);
            }
            const merged = [...prev];
            for (const result of results) {
                const existingIndex = merged.findIndex(item => item.id === result.id);
                if (existingIndex >= 0) {
                    merged[existingIndex] = result;
                } else {
                    merged.push(result);
                }
            }
            return merged.slice().sort(sortByReceivedAt);
        });
    }, []);

    const clearToolResults = useCallback(() => {
        setToolResults([]);
    }, []);

    const value = useMemo<AgentInsightsContextValue>(() => ({
        toolResults,
        recordToolResults,
        clearToolResults,
    }), [toolResults, recordToolResults, clearToolResults]);

    return (
        <AgentInsightsContext.Provider value={value}>
            {children}
        </AgentInsightsContext.Provider>
    );
}

export function useAgentInsights(): AgentInsightsContextValue {
    const context = useContext(AgentInsightsContext);
    if (!context) {
        throw new Error('useAgentInsights must be used within an AgentInsightsProvider');
    }
    return context;
}

function sortByReceivedAt(a: ToolResult, b: ToolResult) {
    const aTime = Date.parse(a.receivedAt);
    const bTime = Date.parse(b.receivedAt);
    if (Number.isNaN(aTime) && Number.isNaN(bTime)) {
        return 0;
    }
    if (Number.isNaN(aTime)) {
        return -1;
    }
    if (Number.isNaN(bTime)) {
        return 1;
    }
    return aTime - bTime;
}
