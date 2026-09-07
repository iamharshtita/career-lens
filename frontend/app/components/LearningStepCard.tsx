/**
 * LearningStepCard — renders one learning step with YouTube and Coursera links.
 * Shows an explicit empty-state message when either resource list is empty.
 */

import { ExternalLink } from "lucide-react";
import type { LearningStep } from "../context/ProfileContext";

interface LearningStepCardProps {
  step: LearningStep;
  rank: number;
}

export default function LearningStepCard({ step, rank }: LearningStepCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      {/* Header */}
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
          {rank}
        </span>
        <h3 className="text-base font-semibold text-gray-900">
          {step.skill_gap}
        </h3>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* YouTube section */}
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-red-600">
            {/* YouTube wordmark colour */}
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
            </svg>
            YouTube
          </h4>
          {step.youtube_resources.length === 0 ? (
            <p className="text-sm text-gray-400 italic">
              No YouTube resources found.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {step.youtube_resources.map((video, i) => (
                <li key={i}>
                  <a
                    href={video.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-start gap-1 text-sm text-blue-600 hover:underline"
                  >
                    <ExternalLink
                      className="mt-0.5 h-3.5 w-3.5 flex-shrink-0"
                      aria-hidden="true"
                    />
                    <span>
                      {video.title}
                      {video.channel && (
                        <span className="ml-1 text-gray-400">
                          — {video.channel}
                        </span>
                      )}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Coursera section */}
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-blue-700">
            {/* Coursera "C" icon */}
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M11.974 0C5.364 0 0 5.364 0 11.974c0 6.61 5.364 11.974 11.974 11.974 6.61 0 11.974-5.364 11.974-11.974C23.948 5.364 18.584 0 11.974 0zm0 4.776c3.977 0 7.198 3.221 7.198 7.198 0 .468-.048.924-.134 1.365l-3.46-2.02a3.642 3.642 0 0 0-3.604-3.143c-1.34 0-2.516.722-3.151 1.797l-3.47-2.026A7.179 7.179 0 0 1 11.974 4.776z" />
            </svg>
            Coursera
          </h4>
          {step.coursera_resources.length === 0 ? (
            <p className="text-sm text-gray-400 italic">
              No Coursera courses found.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {step.coursera_resources.map((course, i) => (
                <li key={i}>
                  <a
                    href={course.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-start gap-1 text-sm text-blue-600 hover:underline"
                  >
                    <ExternalLink
                      className="mt-0.5 h-3.5 w-3.5 flex-shrink-0"
                      aria-hidden="true"
                    />
                    <span>
                      {course.title}
                      {course.provider && (
                        <span className="ml-1 text-gray-400">
                          — {course.provider}
                        </span>
                      )}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
