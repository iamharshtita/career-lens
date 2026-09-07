"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Nav from "../components/Nav";
import { API_BASE_URL } from "../config/api";
import type { AnalysisResult, SkillGap, LearningStep } from "../config/api";
import { useProfile } from "../context/ProfileContext";
import FitScoreGauge from "../components/FitScoreGauge";
import LoadingSpinner from "../components/LoadingSpinner";

// ---------------------------------------------------------------------------
// Stage config
// ---------------------------------------------------------------------------
const STAGES = [
  { key: "job_parsing",     label: "Fetching Job Posting",  agent: "Job Parser Agent",    icon: "🌐" },
  { key: "profile_loading", label: "Loading Profile",        agent: "Profile Agent",       icon: "👤" },
  { key: "gap_analysis",    label: "Analyzing Skill Gaps",   agent: "Gap Analyzer Agent",  icon: "🔍" },
  { key: "learning_path",   label: "Building Learning Path", agent: "Learning Path Agent", icon: "📚" },
  { key: "scoring",         label: "Computing Fit Score",    agent: "Assessor Agent",      icon: "⚖️" },
] as const;
type StageKey = (typeof STAGES)[number]["key"];

interface StageState {
  status: "pending" | "active" | "done";
  logs: string[];
  startedAt: number | null;
  duration: number | null; // ms
}

type PageState =
  | { status: "idle" }
  | { status: "streaming"; stages: Record<StageKey, StageState> }
  | { status: "success"; result: AnalysisResult; stages: Record<StageKey, StageState> }
  | { status: "error"; message: string; stages: Record<StageKey, StageState> | null };

function makeInitialStages(): Record<StageKey, StageState> {
  return Object.fromEntries(
    STAGES.map((s) => [s.key, { status: "pending", logs: [], startedAt: null, duration: null }])
  ) as unknown as Record<StageKey, StageState>;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function JobPage() {
  const { sessionId } = useProfile();
  const [jobUrl, setJobUrl] = useState("");
  const [state, setState] = useState<PageState>({ status: "idle" });
  const sourceRef = useRef<EventSource | null>(null);
  const activeStageRef = useRef<StageKey | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => { sourceRef.current?.close(); }, []);

  function startAnalysis(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionId || !jobUrl.trim()) return;
    sourceRef.current?.close();
    activeStageRef.current = null;
    setState({ status: "streaming", stages: makeInitialStages() });

    const params = new URLSearchParams({ job_url: jobUrl.trim(), session_id: sessionId });
    const source = new EventSource(`${API_BASE_URL}/analysis/analyze?${params}`);
    sourceRef.current = source;

    source.addEventListener("progress", (ev) => {
      const data = JSON.parse((ev as MessageEvent).data) as { stage: StageKey; message: string };
      const now = Date.now();
      setState((prev) => {
        if (prev.status !== "streaming") return prev;
        const stages = { ...prev.stages };
        const prevKey = activeStageRef.current;
        if (prevKey && prevKey !== data.stage && stages[prevKey].status === "active") {
          const dur = stages[prevKey].startedAt ? now - stages[prevKey].startedAt! : null;
          stages[prevKey] = { ...stages[prevKey], status: "done", duration: dur };
        }
        stages[data.stage] = { ...stages[data.stage], status: "active", startedAt: now };
        activeStageRef.current = data.stage;
        return { ...prev, stages };
      });
    });

    source.addEventListener("log", (ev) => {
      const data = JSON.parse((ev as MessageEvent).data) as { stage: string; message: string };
      setState((prev) => {
        if (prev.status !== "streaming") return prev;
        const stages = { ...prev.stages };
        const key = data.stage as StageKey;
        if (stages[key]) {
          stages[key] = { ...stages[key], logs: [...stages[key].logs, data.message] };
        }
        return { ...prev, stages };
      });
      setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
    });

    source.addEventListener("result", (ev) => {
      const result = JSON.parse((ev as MessageEvent).data) as AnalysisResult;
      const now = Date.now();
      setState((prev) => {
        if (prev.status !== "streaming") return prev;
        const stages = { ...prev.stages };
        // Mark ALL stages as done — any that are still "active" get closed out now
        for (const key of Object.keys(stages) as StageKey[]) {
          if (stages[key].status === "active") {
            const dur = stages[key].startedAt ? now - stages[key].startedAt! : null;
            stages[key] = { ...stages[key], status: "done", duration: dur };
          }
        }
        return { status: "success", result, stages };
      });
    });

    source.addEventListener("error", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as { message?: string };
        setState((prev) => ({
          status: "error",
          message: data.message ?? "An error occurred.",
          stages: prev.status === "streaming" ? prev.stages : null,
        }));
      } catch {
        setState((prev) => ({
          status: "error",
          message: "Analysis failed. Check the job URL and your profile.",
          stages: prev.status === "streaming" ? prev.stages : null,
        }));
      }
      source.close();
    });

    source.addEventListener("done", () => { source.close(); });
  }

  const isStreaming = state.status === "streaming";
  const stages =
    state.status === "streaming" || state.status === "success" || state.status === "error"
      ? (state as { stages: Record<StageKey, StageState> | null }).stages
      : null;
  const showPipeline = stages != null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-4 py-10">

        {/* Page header */}
        <div className="mb-8 animate-fade-up">
          <h1 className="serif italic text-3xl text-gray-900">Analyze a Job</h1>
          <p className="mt-1 text-sm text-gray-500">Paste any job URL — LinkedIn, Greenhouse, Workday, Lever…</p>
        </div>

        {/* No profile guard */}
        {!sessionId && (
          <div className="card rounded-2xl border-amber-200 bg-amber-50 px-6 py-5 text-sm text-amber-800 animate-fade-up">
            <p className="font-semibold">No résumé uploaded yet.</p>
            <p className="mt-1 text-amber-700">
              <Link href="/profile" className="underline underline-offset-2">Upload your résumé</Link>{" "}
              to get started.
            </p>
          </div>
        )}

        {/* URL form */}
        {sessionId && (
          <form onSubmit={startAnalysis} className="flex gap-3 animate-fade-up stagger-1">
            <div className="relative min-w-0 flex-1">
              <div className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center">
                <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
                </svg>
              </div>
              <input
                type="url"
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)}
                placeholder="https://boards.greenhouse.io/company/jobs/12345"
                required
                disabled={isStreaming}
                className="w-full rounded-xl border border-gray-200 bg-white pl-10 pr-4 py-3 text-sm text-gray-900 placeholder-gray-400 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:opacity-50 transition shadow-sm"
              />
            </div>
            <button
              type="submit"
              disabled={isStreaming || !jobUrl.trim()}
              className="flex-shrink-0 rounded-xl gradient-accent px-6 py-3 text-sm font-semibold text-white shadow-md shadow-indigo-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
            >
              {isStreaming ? (
                <span className="flex items-center gap-2">
                  <LoadingSpinner size="h-4 w-4" label="Analyzing" />
                  Analyzing…
                </span>
              ) : "Analyze"}
            </button>
          </form>
        )}

        {/* ── Agent pipeline ───────────────────────────────────── */}
        {showPipeline && stages && (
          <div className="mt-8 space-y-2.5 animate-fade-up stagger-2">
            {STAGES.map(({ key, label, agent, icon }, idx) => {
              const s = stages[key];
              const isDone    = s.status === "done";
              const isActive  = s.status === "active";
              const isPending = s.status === "pending";

              return (
                <div
                  key={key}
                  className={`overflow-hidden rounded-2xl border transition-all duration-400 ${
                    isActive
                      ? "border-indigo-200 bg-[#fafafe] shadow-sm shadow-indigo-100"
                      : isDone
                      ? "border-gray-100 bg-white"
                      : "border-gray-100 bg-white opacity-50"
                  }`}
                  style={isActive ? { borderLeftWidth: 4, borderLeftColor: "#6366f1" } : isDone ? { borderLeftWidth: 4, borderLeftColor: "#10b981" } : {}}
                >
                  {/* Header row */}
                  <div className="flex items-center gap-3 px-5 py-3.5">
                    {/* Status icon */}
                    <div className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full transition-all ${
                      isDone
                        ? "bg-emerald-50 ring-1 ring-emerald-200"
                        : isActive
                        ? "bg-indigo-50 ring-1 ring-indigo-200"
                        : "bg-gray-50 ring-1 ring-gray-200"
                    }`}>
                      {isDone ? (
                        <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                        </svg>
                      ) : isActive ? (
                        <LoadingSpinner size="h-4 w-4" label={`Running ${agent}`} />
                      ) : (
                        <span className="text-xs font-bold text-gray-400">{idx + 1}</span>
                      )}
                    </div>

                    {/* Icon + label */}
                    <span className="text-base" aria-hidden>{icon}</span>
                    <span className={`flex-1 text-sm font-semibold ${
                      isDone ? "text-gray-700" : isActive ? "text-gray-900" : "text-gray-400"
                    }`}>
                      {label}
                    </span>

                    {/* Right side: timer / duration + agent badge */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {isDone && s.duration != null && (
                        <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
                          {formatMs(s.duration)}
                        </span>
                      )}
                      {isActive && <LiveTimer startedAt={s.startedAt!} />}
                      {(isActive || isDone) && (
                        <span className={`hidden sm:inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${
                          isActive
                            ? "bg-indigo-50 text-indigo-700 ring-indigo-200"
                            : "bg-gray-50 text-gray-600 ring-gray-200"
                        }`}>
                          {isActive && (
                            <span className="mr-1.5 mt-0.5 h-1.5 w-1.5 rounded-full bg-indigo-500 animate-pulse-soft inline-block" />
                          )}
                          {agent}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Log panel */}
                  {s.logs.length > 0 && (isActive || isDone) && (
                    <div className={`border-t px-5 py-3 ${isActive ? "border-indigo-100" : "border-gray-50"}`}>
                      <div className="max-h-28 space-y-1 overflow-y-auto font-mono text-xs leading-relaxed">
                        {s.logs.map((line, i) => (
                          <div
                            key={i}
                            className={`transition-all animate-slide-in ${
                              isActive && i === s.logs.length - 1
                                ? "text-indigo-600 font-medium"
                                : "text-gray-500"
                            }`}
                          >
                            {line}
                          </div>
                        ))}
                        {isActive && (
                          <span className="cursor-blink text-indigo-500">▊</span>
                        )}
                        <div ref={logEndRef} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Error */}
        {state.status === "error" && (
          <div role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span className="font-semibold">Error: </span>{state.message}
          </div>
        )}

        {/* ── Results ─────────────────────────────────────────── */}
        {state.status === "success" && (
          <div className="mt-10 space-y-8 animate-fade-up">

            {/* Fit Score hero */}
            <div className="card-elevated p-8 text-center">
              <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-gray-400">Match Score</p>
              <div className="flex justify-center">
                <FitScoreGauge score={state.result.fit_score} />
              </div>
              <p className="mt-3 text-xs text-gray-400">
                Based on skills, experience, and qualifications analysis
              </p>
            </div>

            {/* Skill gaps */}
            {state.result.skill_gaps.length > 0 && (
              <div>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-base font-semibold text-gray-900">Skill Gaps</h2>
                  <span className="text-xs text-gray-400">{state.result.skill_gaps.length} identified</span>
                </div>
                <div className="space-y-2">
                  {state.result.skill_gaps.map((gap) => (
                    <SkillGapRow key={gap.skill} gap={gap} />
                  ))}
                </div>
              </div>
            )}

            {/* Learning path */}
            {state.result.learning_path.length > 0 && (
              <div>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-base font-semibold text-gray-900">Learning Path</h2>
                  <span className="text-xs text-gray-400">{state.result.learning_path.length} steps</span>
                </div>
                <div className="space-y-2">
                  {state.result.learning_path.map((step) => (
                    <LearningCard key={step.skill_gap} step={step} />
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end">
              <Link href="/dashboard" className="text-sm text-indigo-600 hover:text-indigo-500 font-medium transition">
                View all analyses →
              </Link>
            </div>
          </div>
        )}
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Live timer component
// ---------------------------------------------------------------------------
function LiveTimer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(Date.now() - startedAt), 100);
    return () => clearInterval(id);
  }, [startedAt]);
  return (
    <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200 tabular-nums">
      {formatMs(elapsed)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Skill gap row
// ---------------------------------------------------------------------------
function SkillGapRow({ gap }: { gap: SkillGap }) {
  const config = {
    critical:       { label: "Critical",      border: "border-red-400",   bg: "bg-red-50",   badge: "bg-red-50 text-red-700 ring-red-200" },
    important:      { label: "Important",     border: "border-amber-400", bg: "bg-amber-50", badge: "bg-amber-50 text-amber-700 ring-amber-200" },
    "nice-to-have": { label: "Nice to have",  border: "border-gray-300",  bg: "bg-gray-50",  badge: "bg-gray-50 text-gray-600 ring-gray-200" },
  }[gap.criticality] ?? { label: gap.criticality, border: "border-gray-300", bg: "bg-white", badge: "bg-gray-50 text-gray-600 ring-gray-200" };

  return (
    <div className={`flex items-center gap-3 rounded-xl border bg-white px-4 py-3 hover:shadow-sm transition-all border-l-4 ${config.border}`}>
      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-bold text-gray-500">
        {gap.rank}
      </span>
      <span className="flex-1 text-sm font-medium text-gray-800">{gap.skill}</span>
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${config.badge}`}>
        {config.label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Learning step card (collapsible accordion)
// ---------------------------------------------------------------------------
function LearningCard({ step }: { step: LearningStep }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-5 py-3.5 text-left hover:bg-gray-50 transition"
      >
        <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-bold text-indigo-600 ring-1 ring-indigo-200">
          {step.priority}
        </span>
        <span className="flex-1 text-sm font-semibold text-gray-800">{step.skill_gap}</span>
        <span className="text-xs text-gray-400">
          {step.youtube_resources.length} video{step.youtube_resources.length !== 1 ? "s" : ""} · 1 course
        </span>
        <svg
          className={`h-4 w-4 text-gray-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19 9-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-gray-100 px-5 py-4 grid gap-5 sm:grid-cols-2 animate-slide-down">
          {/* YouTube */}
          <div>
            <p className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-red-600">
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
              </svg>
              YouTube
            </p>
            {step.youtube_resources.length === 0 ? (
              <p className="text-xs text-gray-400 italic">No results found</p>
            ) : (
              <ul className="space-y-2">
                {step.youtube_resources.map((v, i) => (
                  <li key={i}>
                    <a
                      href={v.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group flex items-start gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 transition"
                    >
                      <svg className="mt-0.5 h-3 w-3 flex-shrink-0 opacity-50 group-hover:opacity-100" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                      </svg>
                      <span>
                        {v.title}{" "}
                        <span className="text-gray-400">— {v.channel}</span>
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Coursera */}
          <div>
            <p className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-blue-700">
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M11.974 0C5.364 0 0 5.364 0 11.974c0 6.61 5.364 11.974 11.974 11.974 6.61 0 11.974-5.364 11.974-11.974C23.948 5.364 18.584 0 11.974 0zm0 4.776c3.977 0 7.198 3.221 7.198 7.198 0 .468-.048.924-.134 1.365l-3.46-2.02a3.642 3.642 0 0 0-3.604-3.143c-1.34 0-2.516.722-3.151 1.797l-3.47-2.026A7.179 7.179 0 0 1 11.974 4.776z" />
              </svg>
              Coursera
            </p>
            {step.coursera_resources.length === 0 ? (
              <p className="text-xs text-gray-400 italic">No courses found</p>
            ) : (
              <ul className="space-y-2">
                {step.coursera_resources.map((c, i) => (
                  <a
                    key={i}
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-start gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 transition"
                  >
                    <svg className="mt-0.5 h-3 w-3 flex-shrink-0 opacity-50 group-hover:opacity-100" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                    </svg>
                    {c.title}
                  </a>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
