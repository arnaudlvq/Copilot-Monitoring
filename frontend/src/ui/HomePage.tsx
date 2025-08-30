import React, { useEffect, useState } from 'react';

// Define an interface for the event structure based on events.jsonl
interface CopilotEvent {
    ts_end: number;
    method: string;
    host: string;
    path: string;
    status: number;
    ttfb_s: number | null;
    latency_total_s: number | null;
    req_bytes: number;
    resp_bytes: number;
    req_ct: string;
    resp_ct: string;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
}

interface Stats {
    totalRequests: number;
    averageLatency: number;
    totalReqBytes: number;
    totalRespBytes: number;
    totalTokens: number;
}

const HomePage: React.FC = () => {
    const [stats, setStats] = useState<Stats>({
        totalRequests: 0,
        averageLatency: 0,
        totalReqBytes: 0,
        totalRespBytes: 0,
        totalTokens: 0,
    });
    const [allEvents, setAllEvents] = useState<CopilotEvent[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws');

        ws.onopen = () => {
            console.log('WebSocket connection established');
            setError(null);
        };

        ws.onmessage = (event) => {
            const newEvent: CopilotEvent = JSON.parse(event.data);
            
            setAllEvents(prevEvents => {
                const updatedEvents = [...prevEvents, newEvent];

                // Recalculate stats based on the new event list
                const totalRequests = updatedEvents.length;
                const totalLatency = updatedEvents.reduce((acc, e) => acc + (e.latency_total_s || 0), 0);
                const totalReqBytes = updatedEvents.reduce((acc, e) => acc + e.req_bytes, 0);
                const totalRespBytes = updatedEvents.reduce((acc, e) => acc + e.resp_bytes, 0);
                const totalTokens = updatedEvents.reduce((acc, e) => acc + (e.total_tokens || 0), 0);

                setStats({
                    totalRequests,
                    averageLatency: totalLatency / totalRequests,
                    totalReqBytes,
                    totalRespBytes,
                    totalTokens,
                });

                return updatedEvents;
            });
        };

        ws.onerror = (err) => {
            console.error('WebSocket error:', err);
            setError('WebSocket connection failed. Is the backend running?');
        };

        ws.onclose = () => {
            console.log('WebSocket connection closed');
        };

        // Clean up the connection when the component unmounts
        return () => {
            ws.close();
        };
    }, []);

    const formatBytes = (bytes: number, decimals = 2) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    };

    if (error) {
        return <div style={{ color: 'red' }}>Error: {error}</div>;
    }

    return (
        <div>
            <h1>Copilot Usage Statistics (Real-time)</h1>
            <div className="card">
                <h2>Summary</h2>
                <p>Total Requests: {stats.totalRequests}</p>
                <p>Total Tokens Used: {stats.totalTokens.toLocaleString()}</p>
                <p>Average Latency: {stats.averageLatency.toFixed(2)}s</p>
                <p>Total Data Sent: {formatBytes(stats.totalReqBytes)}</p>
                <p>Total Data Received: {formatBytes(stats.totalRespBytes)}</p>
            </div>
            {/* Optional: You could add a table here to display allEvents */}
        </div>
    );
};

export default HomePage;