"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import Nav from "../components/Nav";
import { uploadProfile } from "../config/api";
import type { ExtractedProfile } from "../config/api";
import { useProfile } from "../context/ProfileContext";
import LoadingSpinner from "../components/LoadingSpinner";

type PageState = "idle" | "uploading" | "success" | "error";
const MAX_SIZE = 10 * 1024 * 1024;

export default function ProfilePage() {
  const { profile, setProfile, clearProfile } = useProfile();
  const [pageState, setPageState] = useState<PageState>(profile ? "success" : "idle");
  const [error, setError] = useState<string | null>(null);
  const [localProfile, setLocalProfile] = useState<ExtractedProfile | null>(profile);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleUpload(file: File) {
    if (file.type !== "application/pdf") { setError("Only PDF files are supported."); setPageState("error"); return; }
    if (file.size > MAX_SIZE) { setError(`File is ${(file.size / 1024 / 1024).toFixed(1)} MB — max 10 MB.`); setPageState("error"); return; }
    setError(null);
    setPageState("uploading");
    try {
      const { profile: p, session_id } = await uploadProfile(file);
      setProfile(p, session_id);
      setLocalProfile(p);
      setPageState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setPageState("error");
    }
  }

  const activeProfile = localProfile ?? profile;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-4 py-14">

        {/* ── Hero ─────────────────────────────────────────────── */}
        {pageState !== "success" && (
          <div className="mb-12 text-center animate-fade-up">
            <h1 className="serif italic text-5xl text-gray-900 leading-tight mb-3">
              Your Career,{" "}
              <span className="text-gradient">Clarified.</span>
            </h1>
            <p className="text-gray-500 text-base max-w-md mx-auto leading-relaxed">
              Upload your résumé. Paste any job URL. Get your AI-powered fit score,
              skill gaps, and a personalised learning path in seconds.
            </p>
          </div>
        )}

        {/* ── Upload card ───────────────────────────────────────── */}
        <div className={`card p-8 animate-fade-up stagger-1 ${pageState === "success" ? "mb-5" : "mb-0"}`}>
          {pageState !== "success" ? (
            <>
              <h2 className="mb-1 text-base font-semibold text-gray-900">Upload Résumé</h2>
              <p className="mb-5 text-xs text-gray-400">PDF only · max 10 MB</p>

              {/* Drop zone */}
              <label
                className={`flex cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-12 transition-all duration-200 ${
                  dragOver
                    ? "border-indigo-400 bg-indigo-50 shadow-inner"
                    : "border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/40 hover:shadow-sm"
                }`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleUpload(f); }}
              >
                <div className={`flex h-14 w-14 items-center justify-center rounded-2xl transition-all ${
                  dragOver ? "gradient-accent shadow-md shadow-indigo-200" : "bg-indigo-50 ring-1 ring-indigo-200"
                }`}>
                  <svg className={`h-7 w-7 transition-colors ${dragOver ? "text-white" : "text-indigo-500"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.338-2.32 5.75 5.75 0 0 1 5.571 5.57A4.5 4.5 0 0 1 17.25 19.5H6.75z" />
                  </svg>
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-gray-700">
                    Drop your PDF here or{" "}
                    <span className="text-indigo-600 underline underline-offset-2">browse files</span>
                  </p>
                  <p className="mt-1 text-xs text-gray-400">PDF only · max 10 MB</p>
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/pdf"
                  className="sr-only"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); }}
                  disabled={pageState === "uploading"}
                  aria-label="Upload PDF résumé"
                />
              </label>

              {pageState === "uploading" && (
                <div className="mt-6 flex items-center justify-center gap-3">
                  <LoadingSpinner size="h-4 w-4" label="Processing…" />
                  <span className="text-sm text-indigo-600 font-medium">Extracting profile with AI…</span>
                </div>
              )}

              {pageState === "error" && error && (
                <div role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {error}
                </div>
              )}
            </>
          ) : (
            /* Success header */
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 ring-1 ring-emerald-200">
                  <svg className="h-5 w-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-900">Résumé uploaded</p>
                  <p className="text-xs text-gray-400">
                    {activeProfile?.skills.length ?? 0} skills · {activeProfile?.experience_entries.length ?? 0} experience entries
                  </p>
                </div>
              </div>
              <button
                onClick={() => { clearProfile(); setLocalProfile(null); setPageState("idle"); if (fileRef.current) fileRef.current.value = ""; }}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50 hover:border-gray-300 transition"
              >
                Change
              </button>
            </div>
          )}
        </div>

        {/* ── Profile data ─────────────────────────────────────── */}
        {pageState === "success" && activeProfile && (
          <div className="space-y-4 animate-fade-up stagger-2">

            {/* Skills */}
            {activeProfile.skills.length > 0 && (
              <div className="card p-6">
                <h3 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-gray-400">
                  <span className="text-indigo-500">⚡</span>
                  Skills Extracted
                  <span className="ml-auto accent-pill">{activeProfile.skills.length} total</span>
                </h3>
                <div className="flex flex-wrap gap-2">
                  {activeProfile.skills.map((skill) => (
                    <span
                      key={skill}
                      className="accent-pill animate-fade-up"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Experience */}
            {activeProfile.experience_entries.length > 0 && (
              <div className="card p-6">
                <h3 className="mb-5 text-xs font-semibold uppercase tracking-widest text-gray-400 flex items-center gap-2">
                  <span>💼</span> Experience
                </h3>
                <ul className="relative space-y-5">
                  {/* Vertical timeline line */}
                  <div className="absolute left-[5px] top-1 bottom-1 w-px bg-gray-100" aria-hidden />
                  {activeProfile.experience_entries.map((e, i) => (
                    <li key={i} className="flex gap-5 animate-fade-up" style={{ animationDelay: `${i * 0.05}s` }}>
                      {/* Timeline dot */}
                      <div className="mt-1.5 h-2.5 w-2.5 flex-shrink-0 rounded-full bg-indigo-400 ring-2 ring-white z-10" />
                      <div className="flex-1">
                        <p className="text-sm font-semibold text-gray-900">{e.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {e.company}
                          {e.duration_months != null ? ` · ${e.duration_months}mo` : ""}
                        </p>
                        {e.description && (
                          <p className="mt-1.5 text-xs text-gray-500 line-clamp-2 leading-relaxed">{e.description}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Education */}
            {activeProfile.education_details.length > 0 && (
              <div className="card p-6">
                <h3 className="mb-5 text-xs font-semibold uppercase tracking-widest text-gray-400 flex items-center gap-2">
                  <span>🎓</span> Education
                </h3>
                <ul className="relative space-y-5">
                  <div className="absolute left-[5px] top-1 bottom-1 w-px bg-gray-100" aria-hidden />
                  {activeProfile.education_details.map((edu, i) => (
                    <li key={i} className="flex gap-5 animate-fade-up" style={{ animationDelay: `${i * 0.05}s` }}>
                      <div className="mt-1.5 h-2.5 w-2.5 flex-shrink-0 rounded-full bg-violet-400 ring-2 ring-white z-10" />
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          {edu.degree}{edu.field ? ` in ${edu.field}` : ""}
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {edu.institution}{edu.year ? ` · ${edu.year}` : ""}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* CTA */}
            <Link
              href="/job"
              className="flex w-full items-center justify-center gap-2 rounded-xl gradient-accent py-3.5 text-sm font-semibold text-white shadow-md shadow-indigo-200 hover:opacity-90 hover:scale-[1.01] active:scale-100 transition-all duration-150"
            >
              Analyze a Job Posting
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
              </svg>
            </Link>
          </div>
        )}
      </main>
    </>
  );
}
