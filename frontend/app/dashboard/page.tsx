"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Nav from "../components/Nav";
import { listJobs, rescoreJob } from "../config/api";
import type { AnalysisResult } from "../config/api";
import { useProfile } from "../context/ProfileContext";
import LoadingSpinner from "../components/LoadingSpinner";

type FetchState =
  | { status: "loading" }
  | { status: "ready"; jobs: AnalysisResult[] }
  | { status: "error"; message: string };

function scoreConfig(score: number) {
  if (score >= 75) return {
    label: "Strong Match",
    numColor: "text-emerald-600",
    barColor: "bg-emerald-500",
    bgRing: "bg-emerald-50 ring-emerald-200",
    badge: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  };
  if (score >= 50) return {
    label: "Moderate Match",
    numColor: "text-amber-600",
    barColor: "bg-amber-500",
    bgRing: "bg-amber-50 ring-amber-200",
    badge: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  };
  return {
    label: "Needs Work",
    numColor: "text-red-600",
    barColor: "bg-red-500",
    bgRing: "bg-red-50 ring-red-200",
    badge: "bg-red-50 text-red-700 ring-1 ring-red-200",
  };
}

// Animated fill bar
function ScoreBar({ score }: { score: number }) {
  const [width, setWidth] = useState(0);
  const cfg = scoreConfig(score);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Trigger fill animation after mount
    const id = requestAnimationFrame(() => setWidth(score));
    return () => cancelAnimationFrame(id);
  }, [score]);

  return (
    <div ref={ref} className="mt-2.5 h-1.5 w-full rounded-full bg-gray-100">
      <div
        className={`h-1.5 rounded-full transition-all duration-700 ease-out ${cfg.barColor}`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

export default function DashboardPage() {
  const { sessionId } = useProfile();
  const [fetchState, setFetchState] = useState<FetchState>({ status: "loading" });
  const [rescoringId, setRescoringId] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setFetchState({ status: "loading" });
    try {
      const jobs = await listJobs();
      setFetchState({ status: "ready", jobs });
    } catch (err) {
      setFetchState({ status: "error", message: err instanceof Error ? err.message : "Failed to load." });
    }
  }, []);

  useEffect(() => { loadJobs(); }, [loadJobs]);

  async function handleRescore(jobId: string) {
    if (rescoringId || !sessionId) return;
    setRescoringId(jobId);
    try {
      const updated = await rescoreJob(jobId);
      setFetchState((prev) => {
        if (prev.status !== "ready") return prev;
        return { ...prev, jobs: prev.jobs.map((j) => j.job_id === jobId ? updated : j) };
      });
    } catch (err) {
      console.error("Re-score error:", err);
    } finally {
      setRescoringId(null);
    }
  }

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-4 py-10">

        {/* Page header */}
        <div className="mb-8 flex items-center justify-between animate-fade-up">
          <div>
            <h1 className="serif italic text-3xl text-gray-900">Dashboard</h1>
            <p className="mt-1 text-sm text-gray-500">All your analyzed job postings</p>
          </div>
          <button
            onClick={loadJobs}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50 hover:border-gray-300 transition"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
            Refresh
          </button>
        </div>

        {/* Loading */}
        {fetchState.status === "loading" && (
          <div className="flex justify-center py-24 animate-fade-in">
            <div className="flex flex-col items-center gap-3">
              <LoadingSpinner size="h-7 w-7" label="Loading…" />
              <p className="text-xs text-gray-400">Loading analyses…</p>
            </div>
          </div>
        )}

        {/* Error */}
        {fetchState.status === "error" && (
          <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 animate-fade-up">
            {fetchState.message}
            <button onClick={loadJobs} className="ml-3 text-red-600 underline underline-offset-2 font-medium">Retry</button>
          </div>
        )}

        {/* Empty state */}
        {fetchState.status === "ready" && fetchState.jobs.length === 0 && (
          <div className="rounded-2xl border-2 border-dashed border-gray-200 px-8 py-20 text-center animate-fade-up">
            <div className="mb-4 flex justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50 ring-1 ring-indigo-200">
                <svg className="h-8 w-8 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9z" />
                </svg>
              </div>
            </div>
            <p className="text-sm font-semibold text-gray-700">No analyses yet</p>
            <p className="mt-1 text-xs text-gray-400">Analyze your first job to see results here</p>
            <Link
              href="/job"
              className="mt-6 inline-flex items-center gap-2 rounded-xl gradient-accent px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-200 hover:opacity-90 transition"
            >
              Analyze a Job →
            </Link>
          </div>
        )}

        {/* Job cards */}
        {fetchState.status === "ready" && fetchState.jobs.length > 0 && (
          <div className="space-y-3">
            {fetchState.jobs.map((job, i) => {
              const cfg = scoreConfig(job.fit_score);
              const isRescoring = rescoringId === job.job_id;
              const date = new Date(job.rescored_at ?? job.analyzed_at);
              const dateStr = date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

              return (
                <div
                  key={job.job_id}
                  className="card p-5 animate-fade-up"
                  style={{ animationDelay: `${i * 0.05}s` }}
                >
                  <div className="flex items-start gap-4">
                    {/* Score block */}
                    <div className={`flex-shrink-0 flex flex-col items-center justify-center h-14 w-14 rounded-xl ring-1 ${cfg.bgRing}`}>
                      <span className={`text-xl font-extrabold tabular-nums leading-none ${cfg.numColor}`}>
                        {job.fit_score}
                      </span>
                      <span className="mt-0.5 text-[9px] text-gray-400 font-medium uppercase tracking-wide">fit</span>
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.badge}`}>
                          {cfg.label}
                        </span>
                        <span className="text-xs text-gray-400">{dateStr}</span>
                        {job.rescored_at && (
                          <span className="text-xs text-gray-400">· re-scored</span>
                        )}
                      </div>
                      <p className="mt-1.5 text-xs text-gray-500 truncate" title={job.job_id}>
                        {job.skill_gaps.length} gap{job.skill_gaps.length !== 1 ? "s" : ""} identified
                        {job.skill_gaps.length > 0 && (
                          <> · top: <span className="text-gray-700 font-medium">{job.skill_gaps[0]?.skill}</span></>
                        )}
                      </p>
                      {/* Score bar */}
                      <ScoreBar score={job.fit_score} />
                    </div>

                    {/* Re-score button */}
                    <button
                      onClick={() => handleRescore(job.job_id)}
                      disabled={!!rescoringId}
                      className="flex-shrink-0 flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-700 disabled:opacity-50 transition"
                    >
                      {isRescoring ? (
                        <LoadingSpinner size="h-3 w-3" label="Re-scoring" />
                      ) : (
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                        </svg>
                      )}
                      {isRescoring ? "Scoring…" : "Re-score"}
                    </button>
                  </div>
                </div>
              );
            })}

            <div className="pt-4 text-center">
              <Link href="/job" className="text-sm text-indigo-600 hover:text-indigo-500 font-medium transition">
                + Analyze another job
              </Link>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
