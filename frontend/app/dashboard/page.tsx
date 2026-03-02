"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Hexagon,
  Activity,
  CreditCard,
  Zap,
  LogOut,
  Send,
  Loader2,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  FileText,
  AlignLeft
} from "lucide-react";
import { cn } from "@/lib/utils";

// Mock Data structure based on NexusAPI
type Transaction = {
  id: string;
  amount: number;
  description: string;
  created_at: string;
};

type Job = {
  id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: any;
  error?: string;
  created_at: string;
};

export default function Dashboard() {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const [credits, setCredits] = useState<number | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [textToAnalyse, setTextToAnalyse] = useState("");
  const [isAnalysing, setIsAnalysing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  
  const [apiMode, setApiMode] = useState<'analyse' | 'summarise'>('analyse');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [activeSidebarTab, setActiveSidebarTab] = useState<'ledger' | 'jobs'>('ledger');

  const fetchCreditsAndTxns = (t: string) => {
    fetch(`${API_URL}/credits/balance`, {
      headers: { Authorization: `Bearer ${t}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch balance");
        return res.json();
      })
      .then((data) => {
        setCredits(data.balance);
        setTransactions(
          data.recent_transactions.map((tx: any) => ({
            id: tx.id,
            amount: tx.amount,
            description: tx.reason,
            created_at: tx.created_at,
          }))
        );
      })
      .catch((err) => console.error("Credits fetch error:", err));
  };

  useEffect(() => {
    const t = localStorage.getItem("nexus_token");
    if (!t) {
      window.location.href = "/demo";
      return;
    }

    // Fetch user profile
    fetch(`${API_URL}/me`, {
      headers: { Authorization: `Bearer ${t}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Unauthorized");
        return res.json();
      })
      .then((data) => setUser(data))
      .catch((err) => {
        console.error("Auth fetch error:", err);
        localStorage.removeItem("nexus_token");
        window.location.href = "/demo";
      });

    fetchCreditsAndTxns(t);

    const savedJobs = localStorage.getItem("nexus_recent_jobs");
    if (savedJobs) {
      try {
        const parsedJobs: Job[] = JSON.parse(savedJobs);
        setJobs(parsedJobs);
        // Resume polling if there's a pending job
        const pendingJob = parsedJobs.find(j => j.status === 'pending' || j.status === 'running');
        if (pendingJob) {
          setActiveJobId(pendingJob.id);
          setIsAnalysing(true);
        }
      } catch (e) {}
    }
  }, []);

  // Sync jobs to local storage
  useEffect(() => {
    if (jobs.length > 0) {
       localStorage.setItem("nexus_recent_jobs", JSON.stringify(jobs));
    }
  }, [jobs]);

  // Polling for active job
  useEffect(() => {
    let interval: NodeJS.Timeout;
    
    if (activeJobId) {
      interval = setInterval(() => {
        const t = localStorage.getItem("nexus_token");
        fetch(`${API_URL}/api/jobs/${activeJobId}`, {
          headers: { Authorization: `Bearer ${t}` }
        })
        .then(r => r.json())
        .then(data => {
            // Map the API Response to our local Job format
            const mappedJob: Job = {
              id: data.job_id,
              type: 'summarise', // Default since it's the only async job now
              status: data.status,
              result: data.result,
              error: data.error,
              created_at: data.created_at
            };

            setJobs(prevJobs => {
               const exists = prevJobs.find(j => j.id === mappedJob.id);
               if (exists) {
                 return prevJobs.map(j => j.id === mappedJob.id ? mappedJob : j);
               }
               return [mappedJob, ...prevJobs];
            });

            if (mappedJob.status === 'completed' || mappedJob.status === 'failed') {
               setActiveJobId(null);
               setIsAnalysing(false);
               if (mappedJob.status === 'completed') {
                 setAnalysisResult(mappedJob.result);
               } else {
                 setAnalysisResult({ error: mappedJob.error });
               }
               fetchCreditsAndTxns(t!);
            }
        })
        .catch(err => {
            console.error(err);
        });
      }, 2000);
    }
    
    return () => clearInterval(interval);
  }, [activeJobId]);

  const handleAPIRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textToAnalyse) return;

    setIsAnalysing(true);
    setAnalysisResult(null);
    const t = localStorage.getItem("nexus_token");

    const endpoint = apiMode === 'analyse' ? '/api/analyse' : '/api/summarise';
    
    try {
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify({ text: textToAnalyse }),
      });
      
      const data = await res.json();
      
      if (!res.ok) {
        setAnalysisResult({ error: data.error || "Request failed." });
        setIsAnalysing(false);
      } else {
        if (apiMode === 'analyse') {
          // Synchronous response
          setAnalysisResult(data);
          fetchCreditsAndTxns(t!);
          setIsAnalysing(false);
          setTextToAnalyse("");
        } else {
          // Asynchronous response - gets job_id
          const newJob: Job = {
            id: data.job_id,
            type: 'summarise',
            status: 'pending',
            created_at: new Date().toISOString()
          };
          setJobs(prev => [newJob, ...prev]);
          setActiveJobId(data.job_id);
          setActiveSidebarTab('jobs'); // Switch tab to show the new pending job
          setTextToAnalyse(""); 
        }
      }
    } catch (err: any) {
      setAnalysisResult({ error: err.message });
      setIsAnalysing(false);
    }
  };

  const getJobStatusIcon = (status: string) => {
    switch(status) {
      case 'completed': return <CheckCircle2 className="w-4 h-4 text-green-400" />;
      case 'failed': return <XCircle className="w-4 h-4 text-red-400" />;
      default: return <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />;
    }
  };

  return (
    <div className="min-h-screen bg-black text-white selection:bg-white/30 font-sans">
      {/* Background Effects */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.05)_0%,_transparent_100%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_50%_at_50%_0%,_rgba(0,255,255,0.03)_0%,_transparent_100%)]" />
        {/* Subtle grid pattern */}
        <div 
          className="absolute inset-0 opacity-[0.03]"
          style={{ backgroundImage: 'radial-gradient(circle at center, white 1px, transparent 1px)', backgroundSize: '40px 40px' }}
        />
      </div>

      <div className="relative z-10 flex flex-col min-h-screen p-6 md:p-12 lg:px-24 max-w-7xl mx-auto space-y-12">
        {/* Header */}
        <header className="flex justify-between items-center py-4 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-white/10 to-white/5 flex items-center justify-center border border-white/10">
              <Hexagon className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">
                {user ? user.organisation_name : "NexusAPI"}
              </h1>
              <p className="text-xs text-white/50">
                {user ? `${user.name} (${user.role})` : "Admin Workspace"}
              </p>
            </div>
          </div>
          <button 
            onClick={() => {
              localStorage.removeItem("nexus_token");
              window.location.href = '/demo';
            }}
            className="flex items-center gap-2 px-4 py-2 text-sm text-white/70 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 rounded-full transition-all"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out</span>
          </button>
        </header>

        {/* Top Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-md relative overflow-hidden group"
          >
            <div className="absolute top-0 right-0 p-6 opacity-20 group-hover:opacity-40 transition-opacity">
              <Zap className="w-12 h-12" />
            </div>
            <p className="text-sm text-white/50 font-medium mb-1 relative z-10">Available Credits</p>
            <h2 className="text-4xl font-light tracking-tight text-white relative z-10">
              {credits !== null ? credits : <Loader2 className="w-8 h-8 animate-spin" />}
            </h2>
            <div className="mt-4 flex items-center gap-2 text-xs text-green-400 bg-green-400/10 w-max px-2 py-1 rounded-full relative z-10">
              <Activity className="w-3 h-3" />
              <span>Active</span>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
            className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-md"
          >
            <p className="text-sm text-white/50 font-medium mb-1">API Tier</p>
            <h2 className="text-3xl font-light tracking-tight text-white mt-2">
              Pro Plan
            </h2>
            <p className="text-sm text-white/40 mt-4">Async + Sync Enabled</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3 }}
            className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-md"
          >
            <p className="text-sm text-white/50 font-medium mb-1">Total Transactions</p>
            <h2 className="text-3xl font-light tracking-tight text-white mt-2">
              {transactions.length}
            </h2>
            <p className="text-sm text-white/40 mt-4">Lifetime usage history</p>
          </motion.div>
        </div>

        {/* Main Content Area */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 pt-6">
          {/* Left Column: API Playground */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className="space-y-6"
          >
            <div>
              <h3 className="text-xl font-semibold mb-2 flex items-center gap-2">
                <Send className="w-5 h-5 text-white/70" />
                API Playground
              </h3>
              <p className="text-sm text-white/50">
                Execute algorithms on your datasets in real-time.
              </p>
            </div>

            <div className="p-1 rounded-2xl bg-gradient-to-b from-white/10 to-transparent">
              <div className="p-6 rounded-xl bg-[#0a0a0a] border border-white/5 space-y-6">
                
                {/* Mode Selector */}
                <div className="flex bg-white/5 p-1 rounded-lg border border-white/10">
                  <button
                    type="button"
                    onClick={() => setApiMode('analyse')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-medium transition-all ${apiMode === 'analyse' ? 'bg-white/10 text-white shadow-sm' : 'text-white/50 hover:text-white/80'}`}
                  >
                    <FileText className="w-4 h-4" />
                    Analyse (Sync)
                  </button>
                  <button
                    type="button"
                    onClick={() => setApiMode('summarise')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-medium transition-all ${apiMode === 'summarise' ? 'bg-white/10 text-white shadow-sm' : 'text-white/50 hover:text-white/80'}`}
                  >
                    <AlignLeft className="w-4 h-4" />
                    Summarise (Async)
                  </button>
                </div>

                <form onSubmit={handleAPIRequest} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-white/50 uppercase tracking-wider mb-2 flex justify-between">
                      <span>{apiMode === 'analyse' ? 'Text to Analyse' : 'Text to Summarise'}</span>
                      <span className="text-yellow-500/80">{apiMode === 'analyse' ? 'Cost: 25 Credits' : 'Cost: 10 Credits'}</span>
                    </label>
                    <textarea
                      value={textToAnalyse}
                      onChange={(e) => setTextToAnalyse(e.target.value)}
                      placeholder={apiMode === 'analyse' ? "Enter text here... e.g. 'I absolutely love this new feature!'" : "Enter a long document here to be summarized via background workers..."}
                      className="w-full h-32 bg-black/50 border border-white/10 rounded-xl p-4 text-white placeholder:text-white/30 focus:outline-none focus:border-white/30 focus:ring-1 focus:ring-white/30 resize-none transition-all"
                    />
                  </div>
                  
                  <button
                    disabled={isAnalysing || !textToAnalyse}
                    type="submit"
                    className="w-full bg-white text-black font-semibold rounded-xl py-3 px-4 flex items-center justify-center gap-2 hover:bg-white/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isAnalysing && apiMode === 'analyse' ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        {apiMode === 'analyse' ? 'Run Analysis' : 'Dispatch Async Job'}
                        <span className="text-black/50 ml-2">{apiMode === 'analyse' ? '-25 Credits' : '-10 Credits'}</span>
                      </>
                    )}
                  </button>
                </form>

                {/* Results Section */}
                <AnimatePresence>
                  {(analysisResult || (activeJobId && apiMode === 'summarise')) && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="pt-6 border-t border-white/10"
                    >
                      <h4 className="text-xs font-medium text-white/50 uppercase tracking-wider mb-3 flex justify-between items-center">
                        <span>{apiMode === 'analyse' ? 'JSON Response -> /api/analyse' : 'Async Job Result -> /api/summarise'}</span>
                        {activeJobId && apiMode === 'summarise' && (
                          <span className="flex items-center gap-2 text-blue-400 normal-case tracking-normal">
                             <RefreshCw className="w-3 h-3 animate-spin" /> Polling...
                          </span>
                        )}
                      </h4>
                      <pre className="bg-[#111] border border-white/10 p-4 rounded-xl text-sm font-mono text-green-400 overflow-x-auto min-h-[4rem]">
                        {activeJobId && apiMode === 'summarise' && !analysisResult ? (
                          <div className="text-yellow-400/80">Job is currently running in the background...</div>
                        ) : (
                          <code>{JSON.stringify(analysisResult, null, 2)}</code>
                        )}
                      </pre>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>

          {/* Right Column: Transactions & Jobs */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.5 }}
            className="space-y-6"
          >
            {/* Tab selector for the right panel */}
            <div className="flex items-center gap-6 mb-2 border-b border-white/10 pb-2">
              <button 
                onClick={() => setActiveSidebarTab('ledger')}
                className={`text-xl font-semibold flex items-center gap-2 pb-2 -mb-[9px] transition-colors ${activeSidebarTab === 'ledger' ? 'text-white border-b-2 border-white' : 'text-white/50 hover:text-white/80'}`}
              >
                <CreditCard className="w-5 h-5" />
                Ledger History
              </button>
              <button 
                onClick={() => setActiveSidebarTab('jobs')}
                className={`text-xl font-semibold flex items-center gap-2 pb-2 -mb-[9px] transition-colors ${activeSidebarTab === 'jobs' ? 'text-white border-b-2 border-white' : 'text-white/50 hover:text-white/80'}`}
              >
                <Clock className="w-5 h-5" />
                Job History
              </button>
            </div>

            <div className="border border-white/10 bg-white/[0.02] rounded-2xl overflow-hidden backdrop-blur-md h-[500px] overflow-y-auto">
              
              {activeSidebarTab === 'ledger' && (
                <div className="divide-y divide-white/10">
                  {transactions.map((tx) => (
                    <div key={tx.id} className="p-4 flex items-center justify-between hover:bg-white/[0.04] transition-colors">
                      <div className="flex items-center gap-4">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${tx.amount > 0 ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                          {tx.amount > 0 ? "+" : "-"}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-white/90 truncate max-w-[200px]">{tx.description}</p>
                          <p className="text-xs text-white/40">
                            {new Date(tx.created_at).toLocaleString()}
                          </p>
                        </div>
                      </div>
                      <div className={`font-mono font-medium ${tx.amount > 0 ? "text-green-400" : "text-white"}`}>
                        {tx.amount > 0 ? "+" : ""}{tx.amount}
                      </div>
                    </div>
                  ))}
                  {transactions.length === 0 && (
                    <div className="p-8 text-center text-white/40 text-sm">
                      No transactions yet.
                    </div>
                  )}
                </div>
              )}

              {activeSidebarTab === 'jobs' && (
                <div className="divide-y divide-white/10">
                  {jobs.map((job) => (
                    <div key={job.id} className="p-4 flex flex-col gap-3 hover:bg-white/[0.04] transition-colors">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          {getJobStatusIcon(job.status)}
                          <div>
                            <p className="text-sm font-medium text-white/90 flex items-center gap-2">
                              {(job.type || 'summarise').toUpperCase()} Job 
                              <span className="text-[10px] font-mono text-white/30 bg-white/5 px-2 py-0.5 rounded-full">{job.id ? job.id.substring(0,8) : '???'}</span>
                            </p>
                            <p className="text-xs text-white/40">
                              {new Date(job.created_at).toLocaleString()}
                            </p>
                          </div>
                        </div>
                        <div className={`text-xs font-medium uppercase tracking-wider bg-white/5 px-2 py-1 rounded-md
                          ${job.status === 'completed' ? 'text-green-400' : 
                            job.status === 'failed' ? 'text-red-400' : 'text-blue-400'}`}>
                          {job.status}
                        </div>
                      </div>
                      
                      {job.status === 'completed' && job.result && (
                        <div className="pl-7">
                          <p className="text-xs text-white/60 line-clamp-2 italic border-l-2 border-white/10 pl-3">
                            "{job.result.summary || job.result.result || "Executed."}"
                          </p>
                        </div>
                      )}
                      
                      {job.status === 'failed' && job.error && (
                        <div className="pl-7">
                          <p className="text-xs text-red-400/80 line-clamp-2 border-l-2 border-red-500/20 pl-3">
                            {job.error}
                          </p>
                        </div>
                      )}
                    </div>
                  ))}
                  
                  {jobs.length === 0 && (
                    <div className="p-8 text-center text-white/40 text-sm">
                      No background jobs yet.
                    </div>
                  )}
                </div>
              )}

            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
