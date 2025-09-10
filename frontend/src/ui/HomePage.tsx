import React, { useEffect, useState } from 'react';
import {
    HiArrowUp,
    HiArrowDown,
    HiClock,
    HiServer,
    HiChip,
    HiCode,
    HiLightningBolt
} from "react-icons/hi";

import { Activity, TrendingUp, Zap, Trees, Gauge, AlertTriangle, CheckCircle } from 'lucide-react';

// Define interfaces for the event structure
interface Usage {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    reasoning_tokens?: number; // For models like Gemini
}

interface HeatmapData {
    date: string;
    count: number; // Total tokens for that day
}

interface CopilotEvent {
    ts_end: number;
    method: string;
    host: string;
    path: string;
    status: number;
    ttfb_s: number | null;
    latency_total_s: number | null;
    streaming_duration_s: number | null;
    output_tps: number | null;
    req_bytes: number;
    resp_bytes: number;
    req_ct: string;
    resp_ct: string;
    req_json: {
        model?: string;
        // For completion requests which have tokens in `extra`
        extra?: {
            prompt_tokens?: number;
        }
    } | null;
    resp_json: {
        usage?: Usage | null;
        model?: string;
    } | null;
}

interface Stats {
    totalRequests: number;
    averageLatency: number;
    averageStreamingDuration: number;
    averageOutputTps: number;
    totalReqBytes: number;
    totalRespBytes: number;
    totalTokens: number;
    totalPromptTokens: number;
    totalCompletionTokens: number;
    totalReasoningTokens: number;
    models: Record<string, {
        count: number;
        total: number;
        prompt: number;
        completion: number;
        reasoning: number;
        // For TPS calculation
        totalStreamingDuration: number;
        streamingEventsCount: number;
        completionTokensForTps: number;
    }>;
}

const initialStats: Stats = {
    totalRequests: 0,
    averageLatency: 0,
    averageStreamingDuration: 0,
    averageOutputTps: 0,
    totalReqBytes: 0,
    totalRespBytes: 0,
    totalTokens: 0,
    totalPromptTokens: 0,
    totalCompletionTokens: 0,
    totalReasoningTokens: 0,
    models: {},
};

interface ConsumptionProps {
    events: CopilotEvent[];
}

const InstantConsumptionPanel: React.FC<ConsumptionProps> = ({ events }) => {
    const [metrics, setMetrics] = useState({
        score: 0,
        tokensLastHour: 0,
        requestsLastHour: 0,
        avgTokensPerRequest: 0,
        trend: 0
    });
    const [animateIn, setAnimateIn] = useState(false);

    useEffect(() => {
        const calculateConsumption = () => {
            const now = Date.now() / 1000;
            const oneHourAgo = now - 3600;
            const fiveMinAgo = now - 300;

            // Filter events from last hour
            const recentEvents = events.filter(e => e.ts_end > oneHourAgo);
            const veryRecentEvents = events.filter(e => e.ts_end > fiveMinAgo);

            // Calculate metrics
            const requestsLastHour = recentEvents.length;
            const tokensLastHour = recentEvents.reduce((acc, event) => {
                const usage = event.resp_json?.usage;
                const promptTokens = usage?.prompt_tokens ?? event.req_json?.extra?.prompt_tokens ?? 0;
                const completionTokens = usage?.completion_tokens ?? 0;
                const reasoningTokens = usage?.reasoning_tokens ?? 0;
                return acc + (usage?.total_tokens ?? (promptTokens + completionTokens + reasoningTokens));
            }, 0);

            const tokensLast5Min = veryRecentEvents.reduce((acc, event) => {
                const usage = event.resp_json?.usage;
                const promptTokens = usage?.prompt_tokens ?? event.req_json?.extra?.prompt_tokens ?? 0;
                const completionTokens = usage?.completion_tokens ?? 0;
                const reasoningTokens = usage?.reasoning_tokens ?? 0;
                return acc + (usage?.total_tokens ?? (promptTokens + completionTokens + reasoningTokens));
            }, 0);

            // Calculate consumption score (weighted formula)
            const calculatedScore = (tokensLastHour / 100) + (requestsLastHour * 30);

            // Calculate trend (comparing last 5 min to previous 5 min)
            const trend = tokensLast5Min * 2 - tokensLastHour;

            setMetrics({
                score: calculatedScore,
                tokensLastHour,
                requestsLastHour,
                avgTokensPerRequest: requestsLastHour > 0 ? Math.round(tokensLastHour / requestsLastHour) : 0,
                trend: trend
            });
        };

        calculateConsumption();
        if (!animateIn) {
            setAnimateIn(true);
        }

        // Recalculate stats every 4 minutes to update the sliding time window
        const interval = setInterval(calculateConsumption, 240000); // 4 minutes
        return () => clearInterval(interval);
    }, [events]);

    const getHealthStatus = () => {
        if (metrics.score > 10000) return { status: 'Critical', color: 'text-red-500 bg-red-500/10', icon: AlertTriangle };
        if (metrics.score > 5000) return { status: 'High', color: 'text-yellow-500 bg-yellow-500/10', icon: AlertTriangle };
        if (metrics.score > 1000) return { status: 'Moderate', color: 'text-orange-400 bg-orange-400/10', icon: Activity };
        return { status: 'Optimal', color: 'text-green-400 bg-green-400/10', icon: CheckCircle };
    };

    const getTreeCount = () => {
        // Maximum score for visualization purposes, where the forest is gone.
        const maxScoreForForest = 12000;
        const totalTrees = 40;

        // Calculate the percentage of "damage" to the forest.
        // Clamp the score between 0 and maxScoreForForest.
        const scoreRatio = Math.min(Math.max(metrics.score, 0), maxScoreForForest) / maxScoreForForest;

        // The number of trees is inversely proportional to the score.
        const remainingTrees = totalTrees * (1 - scoreRatio);

        return Math.round(remainingTrees);
    };

    const healthStatus = getHealthStatus();
    const treeCount = getTreeCount();
    const StatusIcon = healthStatus.icon;

    return (
        <div className={`bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-6 mb-12 rounded-xl shadow-2xl border border-gray-700/50 transition-all duration-500 ${animateIn ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-gradient-to-br from-green-500/20 to-blue-500/20 rounded-lg">
                        <Gauge className="w-5 h-5 text-green-400" />
                    </div>
                    <div>
                        <h3 className="text-white text-lg font-semibold">Real-time Consumption Monitor</h3>
                        <p className="text-gray-400 text-sm">Last 60 minutes activity</p>
                    </div>
                </div>
                <div className={`flex items-center gap-2 px-3 py-1 rounded-full ${healthStatus.color}`}>
                    <StatusIcon className="w-4 h-4" />
                    <span className="text-sm font-medium">{healthStatus.status}</span>
                </div>
            </div>

            {/* Main Metrics Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
                {/* Score Card */}
                <div className="bg-gray-800/50 backdrop-blur rounded-lg p-4 border border-gray-700/50">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-gray-400 text-sm">Consumption Score</span>
                        <Zap className="w-4 h-4 text-yellow-500" />
                    </div>
                    <div className={`text-3xl font-bold ${healthStatus.color.split(' ')[0]}`}>
                        {Math.round(metrics.score).toLocaleString()}
                    </div>
                    <div className="flex items-center gap-1 mt-2">
                        {metrics.trend > 0 ? (
                            <TrendingUp className="w-4 h-4 text-red-400" />
                        ) : (
                            <TrendingUp className="w-4 h-4 text-green-400 rotate-180" />
                        )}
                        <span className={`text-xs ${metrics.trend > 0 ? 'text-red-400' : 'text-green-400'}`}>
                            {metrics.trend > 0 ? 'Increasing' : 'Decreasing'}
                        </span>
                    </div>
                </div>

                {/* Tokens Card */}
                <div className="bg-gray-800/50 backdrop-blur rounded-lg p-4 border border-gray-700/50">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-gray-400 text-sm">Tokens Used</span>
                        <Activity className="w-4 h-4 text-blue-500" />
                    </div>
                    <div className="text-3xl font-bold text-white">
                        {(metrics.tokensLastHour / 1000).toFixed(1)}K
                    </div>
                    <div className="text-xs text-gray-500 mt-2">
                        Avg: {metrics.avgTokensPerRequest.toLocaleString()} per request
                    </div>
                </div>

                {/* Requests Card */}
                <div className="bg-gray-800/50 backdrop-blur rounded-lg p-4 border border-gray-700/50">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-gray-400 text-sm">API Requests</span>
                        <TrendingUp className="w-4 h-4 text-purple-500" />
                    </div>
                    <div className="text-3xl font-bold text-white">
                        {metrics.requestsLastHour}
                    </div>
                    <div className="text-xs text-gray-500 mt-2">
                        ~{Math.round(metrics.requestsLastHour / 60)} per minute
                    </div>
                </div>
            </div>

            {/* Forest Visualization */}
            <div className="bg-gradient-to-b from-gray-800/30 to-gray-900/50 rounded-lg p-4 border border-gray-700/50">
                <div className="flex items-center gap-2 mb-3">
                    <Trees className="w-4 h-4 text-green-400" />
                    <span className="text-sm text-gray-400">Environmental Impact Visualization</span>
                </div>
                
                <div className="relative h-24 bg-gradient-to-b from-sky-900/20 to-green-900/20 rounded-lg overflow-hidden">
                    {/* Sky gradient */}
                    <div className="absolute inset-0 bg-gradient-to-b from-blue-500/5 to-transparent"></div>
                    
                    {/* Trees */}
                    <div className="absolute bottom-0 left-0 right-0 flex items-end justify-center gap-1 p-2">
                        {Array.from({ length: 40 }, (_, i) => (
                            <div
                                key={i}
                                className={`transition-all duration-700 ${
                                    i < treeCount ? 'opacity-100 scale-100' : 'opacity-0 scale-0'
                                }`}
                                style={{ 
                                    transitionDelay: `${i * 20}ms`,
                                    fontSize: `${18 + Math.random() * 8}px`,
                                    marginBottom: `${Math.random() * 8}px`
                                }}
                            >
                                🌲
                            </div>
                        ))}
                    </div>
                </div>
                
                <div className="flex items-center justify-between mt-3">
                    <p className="text-xs text-gray-500">
                        {treeCount}/40 trees remaining
                    </p>
                    <p className="text-xs text-gray-500">
                        Lower consumption = healthier forest
                    </p>
                </div>
            </div>
        </div>
    );
};


const HomePage: React.FC = () => {
    const [stats, setStats] = useState<Stats>(initialStats);
    const [allEvents, setAllEvents] = useState<CopilotEvent[]>([]);
    const [heatmapData, setHeatmapData] = useState<HeatmapData[]>([]);
    const [error, setError] = useState<string | null>(null);

    // Moved outside useEffect to be accessible by both fetch and WebSocket
    const calculateStats = (events: CopilotEvent[]): Stats => {
        if (events.length === 0) return initialStats;

        const newStats: Stats = { ...initialStats, models: {} };

        newStats.totalRequests = events.length;
        newStats.totalReqBytes = events.reduce((acc, e) => acc + e.req_bytes, 0);
        newStats.totalRespBytes = events.reduce((acc, e) => acc + e.resp_bytes, 0);

        const totalLatency = events.reduce((acc, e) => acc + (e.latency_total_s || 0), 0);
        newStats.averageLatency = totalLatency / newStats.totalRequests;

        let totalStreamingDuration = 0;
        let streamingEventsCount = 0;
        let totalOutputTps = 0;
        let tpsEventsCount = 0;

        for (const event of events) {
            const model = event.req_json?.model || event.resp_json?.model || 'unknown';
            if (!newStats.models[model]) {
                newStats.models[model] = { count: 0, total: 0, prompt: 0, completion: 0, reasoning: 0, totalStreamingDuration: 0, streamingEventsCount: 0, completionTokensForTps: 0 };
            }
            newStats.models[model].count++;

            // Aggregate streaming stats
            if (event.streaming_duration_s && event.streaming_duration_s > 0) {
                totalStreamingDuration += event.streaming_duration_s;
                streamingEventsCount++;
                newStats.models[model].totalStreamingDuration += event.streaming_duration_s;
                newStats.models[model].streamingEventsCount++;
            }
            if (event.output_tps && event.output_tps > 0) {
                totalOutputTps += event.output_tps;
                tpsEventsCount++;
            }

            const usage = event.resp_json?.usage;

            // Handle different token structures
            const promptTokens = usage?.prompt_tokens ?? event.req_json?.extra?.prompt_tokens ?? 0;
            const completionTokens = usage?.completion_tokens ?? 0;
            const reasoningTokens = usage?.reasoning_tokens ?? 0;
            const totalTokens = usage?.total_tokens ?? (promptTokens + completionTokens + reasoningTokens);

            // If this was a streaming event, add completion tokens for model-specific TPS calc
            if (event.streaming_duration_s && event.streaming_duration_s > 0) {
                newStats.models[model].completionTokensForTps += completionTokens;
            }

            newStats.models[model].prompt += promptTokens;
            newStats.models[model].completion += completionTokens;
            newStats.models[model].reasoning += reasoningTokens;
            newStats.models[model].total += totalTokens;

            newStats.totalPromptTokens += promptTokens;
            newStats.totalCompletionTokens += completionTokens;
            newStats.totalReasoningTokens += reasoningTokens;
            newStats.totalTokens += totalTokens;
        }

        newStats.averageStreamingDuration = streamingEventsCount > 0 ? totalStreamingDuration / streamingEventsCount : 0;
        newStats.averageOutputTps = tpsEventsCount > 0 ? totalOutputTps / tpsEventsCount : 0;

        return newStats;
    };

    const processEventsForHeatmap = (events: CopilotEvent[]): HeatmapData[] => {
        const dailyTokens: Record<string, number> = {};

        for (const event of events) {
            const date = new Date(event.ts_end * 1000).toISOString().split('T')[0];
            const usage = event.resp_json?.usage;
            const promptTokens = usage?.prompt_tokens ?? event.req_json?.extra?.prompt_tokens ?? 0;
            const completionTokens = usage?.completion_tokens ?? 0;
            const reasoningTokens = usage?.reasoning_tokens ?? 0;
            const totalTokens = usage?.total_tokens ?? (promptTokens + completionTokens + reasoningTokens);

            if (!dailyTokens[date]) {
                dailyTokens[date] = 0;
            }
            dailyTokens[date] += totalTokens;
        }

        return Object.entries(dailyTokens).map(([date, count]) => ({
            date,
            count,
        }));
    };

    useEffect(() => {
        // --- 1. Fetch historical data on load ---
        const fetchHistory = async () => {
            try {
                const response = await fetch('http://localhost:8000/history');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const historicalEvents: CopilotEvent[] = await response.json();
                setAllEvents(historicalEvents);
                setStats(calculateStats(historicalEvents));
                setHeatmapData(processEventsForHeatmap(historicalEvents)); // Process for heatmap
            } catch (e) {
                console.error("Failed to fetch history:", e);
                setError("Could not load historical data. Is the backend running?");
            }
        };

        fetchHistory();

        // --- 2. Connect WebSocket for real-time updates ---
        const ws = new WebSocket('ws://localhost:8000/ws');

        ws.onopen = () => {
            console.log('WebSocket connection established');
            setError(null);
        };

        ws.onmessage = (event) => {
            const newEvent: CopilotEvent = JSON.parse(event.data);

            setAllEvents(prevEvents => {
                const updatedEvents = [...prevEvents, newEvent];
                // The calculateStats function is now more robust
                setStats(calculateStats(updatedEvents));
                setHeatmapData(processEventsForHeatmap(updatedEvents)); // Update heatmap
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

    const StatCard: React.FC<{ title: string; value: string; icon: React.ReactNode }> = ({ title, value, icon }) => (
        <div className="bg-gray-800 p-6 rounded-lg shadow-lg flex items-center space-x-4">
            <div className="bg-gray-700 p-3 rounded-full">
                {icon}
            </div>
            <div>
                <p className="text-gray-400 text-sm font-medium">{title}</p>
                <p className="text-white text-2xl font-bold">{value}</p>
            </div>
        </div>
    );

    const UsageHeatmap: React.FC<{ data: HeatmapData[] }> = ({ data }) => {
        const endDate = new Date();
        const startDate = new Date();
        startDate.setDate(endDate.getDate() - 365);

        const values = data.reduce((acc, val) => {
            acc[val.date] = val.count;
            return acc;
        }, {} as Record<string, number>);

        const maxCount = Math.max(...Object.values(values), 0);

        const getColor = (count: number) => {
            if (count === 0) return 'bg-gray-700'; // Lighter gray for empty cells
            if (maxCount === 0) return 'bg-green-400';
            const ratio = count / maxCount;
            if (ratio > 0.75) return 'bg-green-600';
            if (ratio > 0.5) return 'bg-green-500';
            if (ratio > 0.25) return 'bg-green-400';
            return 'bg-green-300';
        };

        const days = [];
        let currentDate = new Date(startDate);
        currentDate.setDate(currentDate.getDate() - currentDate.getDay());

        while (currentDate <= endDate) {
            const dateString = currentDate.toISOString().split('T')[0];
            const count = values[dateString] || 0;

            if (currentDate >= startDate) {
                 days.push({
                    date: dateString,
                    count: count,
                    color: getColor(count),
                });
            } else {
                 days.push({
                    date: dateString,
                    count: 0,
                    color: 'bg-transparent',
                });
            }
            currentDate.setDate(currentDate.getDate() + 1);
        }

        return (
            <div className="bg-gray-800 p-6 rounded-lg shadow-lg">
                <h3 className="text-white text-lg font-semibold mb-4">Usage Heatmap (Last 365 Days)</h3>
                <div className="grid grid-cols-53 grid-rows-7 gap-1" style={{ gridAutoFlow: 'column' }}>
                    {days.map((day, index) => (
                        <div
                            key={index}
                            className={`w-3 h-3 rounded-sm border border-gray-900/50 ${day.color}`} // Added border
                            title={`${day.date}: ${day.count.toLocaleString()} tokens`}
                        />
                    ))}
                </div>
            </div>
        );
    };

    if (error) {
        return (
            <div className="bg-gray-900 min-h-screen flex items-center justify-center">
                <div className="bg-red-900 border border-red-400 text-red-100 px-4 py-3 rounded-lg shadow-lg" role="alert">
                    <strong className="font-bold">Error:</strong>
                    <span className="block sm:inline ml-2">{error}</span>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-gray-900 text-white min-h-screen p-8 font-sans">
            <div className="max-w-7xl mx-auto">
                <header className="mb-8 flex items-center space-x-6">
                    <img src="/assets/logo.png" alt="Logo" className="h-32" />
                    <div>
                        <h1 className="text-4xl font-bold tracking-tight">Copilot Usage Dashboard</h1>
                        <p className="text-gray-400 mt-1">Real-time statistics of your GitHub Copilot usage.</p>
                    </div>
                </header>

                <InstantConsumptionPanel events={allEvents} />

                <h2 className="text-3xl font-bold tracking-tight text-white mt-12 mb-6">Overall Statistics</h2>

                <main className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* Left Column */}
                    <div className="lg:col-span-2 space-y-8">
                        {/* Stats Cards */}
                        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-3 gap-6">
                            <StatCard title="Total Requests" value={stats.totalRequests.toLocaleString()} icon={<HiServer className="h-6 w-6 text-blue-400" />} />
                            <StatCard title="Avg Latency" value={`${stats.averageLatency.toFixed(2)}s`} icon={<HiClock className="h-6 w-6 text-yellow-400" />} />
                            <StatCard title="Avg Output Speed" value={`${stats.averageOutputTps.toFixed(1)} t/s`} icon={<HiLightningBolt className="h-6 w-6 text-purple-400" />} />
                            <StatCard title="Data Sent" value={formatBytes(stats.totalReqBytes)} icon={<HiArrowUp className="h-6 w-6 text-red-400" />} />
                            <StatCard title="Data Received" value={formatBytes(stats.totalRespBytes)} icon={<HiArrowDown className="h-6 w-6 text-green-400" />} />
                            <StatCard title="Avg Stream Duration" value={`${stats.averageStreamingDuration.toFixed(2)}s`} icon={<HiClock className="h-6 w-6 text-teal-400" />} />
                        </div>

                        {/* Token Usage */}
                        <div className="bg-gray-800 p-6 rounded-lg shadow-lg">
                            <div className="flex justify-between items-center bg-gray-700 p-4 rounded-t-lg">
                                <h3 className="text-white text-lg font-semibold">Token Usage Breakdown</h3>
                                <span className="font-bold text-2xl text-white">{stats.totalTokens.toLocaleString()}</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-gray-700 rounded-b-lg overflow-hidden">
                                <div className="bg-gray-800 p-4">
                                    <p className="text-sm text-blue-400">Input (Prompt)</p>
                                    <p className="text-xl font-semibold">{stats.totalPromptTokens.toLocaleString()}</p>
                                </div>
                                <div className="bg-gray-800 p-4">
                                    <p className="text-sm text-green-400">Output (Completion)</p>
                                    <p className="text-xl font-semibold">{stats.totalCompletionTokens.toLocaleString()}</p>
                                </div>
                                <div className="bg-gray-800 p-4">
                                    <p className="text-sm text-purple-400">Reasoning</p>
                                    <p className="text-xl font-semibold">{stats.totalReasoningTokens > 0 ? stats.totalReasoningTokens.toLocaleString() : 'N/A'}</p>
                                </div>
                            </div>
                        </div>


                        {/* Heatmap */}
                        <UsageHeatmap data={heatmapData} />
                    </div>

                    {/* Right Column */}
                    <div className="bg-gray-800 p-6 rounded-lg shadow-lg">
                        <h3 className="text-white text-lg font-semibold mb-4">Tokens by Model</h3>
                        <div className="space-y-6">
                            {Object.entries(stats.models).length > 0 ? (
                                Object.entries(stats.models)
                                    .sort(([, a], [, b]) => b.total - a.total)
                                    .map(([model, modelStats]) => (
                                        <div key={model} className="bg-gray-700/50 p-4 rounded-lg">
                                            <div className="flex justify-between items-center mb-3">
                                                <h4 className="font-semibold flex items-center text-lg">
                                                    <HiCode className="h-5 w-5 mr-2 text-gray-400" />
                                                    {model}
                                                </h4>
                                                <span className="text-sm bg-gray-600 px-2 py-1 rounded-full">{modelStats.count.toLocaleString()} reqs</span>
                                            </div>

                                            {/* Total Tokens */}
                                            <div className="flex justify-between items-baseline mb-3">
                                                <span className="text-gray-400 text-sm">Total Tokens</span>
                                                <span className="font-bold text-xl">{modelStats.total.toLocaleString()}</span>
                                            </div>

                                            {/* Token Breakdown */}
                                            <div className="space-y-2 mb-3">
                                                <div className="flex justify-between text-sm">
                                                    <span className="text-blue-400">Input</span>
                                                    <span>{modelStats.prompt.toLocaleString()}</span>
                                                </div>
                                                <div className="flex justify-between text-sm">
                                                    <span className="text-green-400">Output</span>
                                                    <span>{modelStats.completion.toLocaleString()}</span>
                                                </div>
                                                {modelStats.reasoning > 0 && (
                                                    <div className="flex justify-between text-sm">
                                                        <span className="text-purple-400">Reasoning</span>
                                                        <span>{modelStats.reasoning.toLocaleString()}</span>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Performance Metrics */}
                                            {modelStats.totalStreamingDuration > 0 && (
                                                <div className="border-t border-gray-600 pt-3 mt-3 space-y-2">
                                                    <div className="flex justify-between text-sm">
                                                        <span className="text-purple-400 flex items-center"><HiLightningBolt className="mr-1"/>Output Speed</span>
                                                        <span className="font-medium">
                                                            {(modelStats.completionTokensForTps / modelStats.totalStreamingDuration).toFixed(1)} t/s
                                                        </span>
                                                    </div>
                                                    <div className="flex justify-between text-sm">
                                                        <span className="text-teal-400 flex items-center"><HiClock className="mr-1"/>Avg Stream</span>
                                                        <span className="font-medium">
                                                            {(modelStats.totalStreamingDuration / modelStats.streamingEventsCount).toFixed(2)}s
                                                        </span>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ))
                            ) : (
                                <p className="text-gray-400 text-center py-8">No model usage recorded yet.</p>
                            )}
                        </div>
                    </div>
                </main>
            </div>
        </div>
    );
};

export default HomePage;