"use client";

/**
 * JobCard — renders a saved job summary card with fit score and re-score action.
 */

import { RefreshCw } from "lucide-react";
import type { AnalysisResult } from "../context/ProfileContext";
import LoadingSpinner from "./LoadingSpinner";

interface JobCardProps {
  result: AnalysisResult;
  onRescore: () => void;
  isRescoring: boolean;
}

function fitScoreClasses(score: number): string {
  if (score >= 75) return "bg-green-100 text-green-700";
  if (score >= 50) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

function fitScoreLabel(score: number): string {
  if (score >= 75) return "Strong Match";
  if (score >= 50) return "Moderate Match";
  return "Needs Work";
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function JobCard({ result, onRescore, isRescoring }: JobCardProps) {
  const scoreClasses = fitScoreClasses(result.fit_score);
  const displayDate = result.rescored_at
    ? formatDate(result.rescored_at)
    : formatDate(result.analyzed_at);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-4">
        {/* Left: job info */}
        <div className="min-w-0">
          {/* job title — AnalysisResult doesn't carry title directly;
              we surface the job_id as a fallback and let the page layer
              enrich this if it has the ParsedJob available. */}
          <p className="truncate text-sm font-semibold text-gray-900">
            Job ID: {result.job_id}
          </p>
          <p className="mt-0.5 text-xs text-gray-400">
            {result.rescored_at ? "Re-scored" : "Analyzed"}:{" "}
            {displayDate}
          </p>
        </div>

        {/* Right: fit score badge */}
        <span
          className={`flex-shrink-0 rounded-full px-3 py-1 text-sm font-bold ${scoreClasses}`}
          aria-label={`Fit score ${result.fit_score} — ${fitScoreLabel(result.fit_score)}`}
        >
          {result.fit_score}%
        </span>
      </div>

      {/* Footer: label + re-score button */}
      <div className="mt-4 flex items-center justify-between">
        <span className={`text-xs font-medium ${scoreClasses} rounded-full px-2.5 py-0.5`}>
          {fitScoreLabel(result.fit_score)}
        </span>

        <button
          type="button"
          onClick={onRescore}
          disabled={isRescoring}
          aria-label="Re-score this job against your current profile"
          className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRescoring ? (
            <LoadingSpinner label="Re-scoring…" size="h-3.5 w-3.5" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {isRescoring ? "Re-scoring…" : "Re-score"}
        </button>
      </div>
    </div>
  );
}
