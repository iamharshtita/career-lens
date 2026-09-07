/**
 * API configuration and typed fetch helpers for the CareerLens backend.
 * All requests target the FastAPI server at API_BASE_URL.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Response types (mirrors backend Pydantic models)
// ---------------------------------------------------------------------------

export interface ExperienceEntry {
  title: string;
  company: string;
  duration_months: number | null;
  description: string;
}

export interface EducationDetail {
  degree: string;
  institution: string;
  year: number | null;
  field: string | null;
}

export interface ExtractedProfile {
  session_id: string;
  skills: string[];
  experience_entries: ExperienceEntry[];
  education_details: EducationDetail[];
  raw_text: string;
  extracted_at: string; // ISO datetime string
}

export interface SkillGap {
  skill: string;
  rank: number;
  criticality: "critical" | "important" | "nice-to-have";
}

export interface VideoResource {
  title: string;
  url: string;
  channel: string;
  duration_seconds: number | null;
}

export interface CourseResource {
  title: string;
  url: string;
  provider: string;
  duration_weeks: number | null;
}

export interface LearningStep {
  skill_gap: string;
  priority: number;
  youtube_resources: VideoResource[];
  coursera_resources: CourseResource[];
}

export interface AnalysisResult {
  result_id: string;
  job_id: string;
  session_id: string;
  fit_score: number;
  skill_gaps: SkillGap[];
  learning_path: LearningStep[];
  analyzed_at: string; // ISO datetime string
  rescored_at: string | null;
}

// ---------------------------------------------------------------------------
// Upload payload / response
// ---------------------------------------------------------------------------

export interface UploadProfileResponse {
  session_id: string;
  profile: ExtractedProfile;
}

// ---------------------------------------------------------------------------
// Generic fetch helper
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new ApiError(response.status, text);
  }
  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Typed API helpers
// ---------------------------------------------------------------------------

/** Upload a PDF resume and return the session_id + extracted profile. */
export async function uploadProfile(
  file: File,
): Promise<UploadProfileResponse> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<UploadProfileResponse>("/profile/upload", {
    method: "POST",
    body,
  });
}

/** Retrieve a stored profile by session_id. */
export async function getProfile(
  sessionId: string,
): Promise<ExtractedProfile> {
  return apiFetch<ExtractedProfile>(`/profile/${sessionId}`);
}

/** List all saved analysis results (sorted by analyzed_at desc on the server). */
export async function listJobs(): Promise<AnalysisResult[]> {
  return apiFetch<AnalysisResult[]>("/dashboard/jobs");
}

/** Get a single analysis result by job_id. */
export async function getJob(jobId: string): Promise<AnalysisResult> {
  return apiFetch<AnalysisResult>(`/dashboard/jobs/${jobId}`);
}

/** Trigger a re-score for an existing job result. */
export async function rescoreJob(jobId: string): Promise<AnalysisResult> {
  return apiFetch<AnalysisResult>(`/dashboard/jobs/${jobId}/rescore`, {
    method: "POST",
  });
}

/**
 * Open an EventSource for the analysis SSE stream.
 * The caller is responsible for closing the source when done.
 */
export function openAnalysisStream(
  jobUrl: string,
  sessionId: string,
): EventSource {
  const params = new URLSearchParams({ job_url: jobUrl, session_id: sessionId });
  return new EventSource(`${API_BASE_URL}/analysis/analyze?${params}`);
}
