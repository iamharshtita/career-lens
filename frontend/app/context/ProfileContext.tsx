"use client";

/**
 * ProfileContext — global state for the active candidate profile.
 *
 * Persists sessionId and profile in localStorage so they survive
 * page navigations and browser refreshes.
 *
 * Keys used in localStorage:
 *   - careerlens_session_id  →  string (UUID)
 *   - careerlens_profile     →  JSON-serialised ExtractedProfile
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

// ---------------------------------------------------------------------------
// Re-export types so components can import from a single place
// ---------------------------------------------------------------------------

export type {
  ExperienceEntry,
  EducationDetail,
  ExtractedProfile,
  SkillGap,
  VideoResource,
  CourseResource,
  LearningStep,
  AnalysisResult,
} from "../config/api";

import type { ExtractedProfile } from "../config/api";

// ---------------------------------------------------------------------------
// Context type
// ---------------------------------------------------------------------------

export interface ProfileContextType {
  /** UUID of the active session, or null if no profile has been uploaded. */
  sessionId: string | null;
  /** The extracted profile, or null if not yet uploaded. */
  profile: ExtractedProfile | null;
  /**
   * Store a new profile and its associated session ID.
   * Persists both values to localStorage.
   */
  setProfile: (profile: ExtractedProfile, sessionId: string) => void;
  /**
   * Clear the active profile and remove all persisted keys from localStorage.
   */
  clearProfile: () => void;
}

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

const LS_SESSION_KEY = "careerlens_session_id";
const LS_PROFILE_KEY = "careerlens_profile";

function loadFromStorage(): {
  sessionId: string | null;
  profile: ExtractedProfile | null;
} {
  try {
    const sessionId = localStorage.getItem(LS_SESSION_KEY);
    const raw = localStorage.getItem(LS_PROFILE_KEY);
    const profile: ExtractedProfile | null = raw ? JSON.parse(raw) : null;
    return { sessionId, profile };
  } catch {
    // localStorage may be unavailable (SSR, private mode, etc.)
    return { sessionId: null, profile: null };
  }
}

function saveToStorage(sessionId: string, profile: ExtractedProfile): void {
  try {
    localStorage.setItem(LS_SESSION_KEY, sessionId);
    localStorage.setItem(LS_PROFILE_KEY, JSON.stringify(profile));
  } catch {
    // Ignore write failures (quota exceeded, etc.)
  }
}

function clearStorage(): void {
  try {
    localStorage.removeItem(LS_SESSION_KEY);
    localStorage.removeItem(LS_PROFILE_KEY);
  } catch {
    // Ignore
  }
}

// ---------------------------------------------------------------------------
// Context creation
// ---------------------------------------------------------------------------

const ProfileContext = createContext<ProfileContextType | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [profile, setProfileState] = useState<ExtractedProfile | null>(null);

  // Restore from localStorage on first render (client-only).
  useEffect(() => {
    const { sessionId: storedSession, profile: storedProfile } =
      loadFromStorage();
    if (storedSession) setSessionId(storedSession);
    if (storedProfile) setProfileState(storedProfile);
  }, []);

  const setProfile = useCallback(
    (newProfile: ExtractedProfile, newSessionId: string) => {
      setSessionId(newSessionId);
      setProfileState(newProfile);
      saveToStorage(newSessionId, newProfile);
    },
    [],
  );

  const clearProfile = useCallback(() => {
    setSessionId(null);
    setProfileState(null);
    clearStorage();
  }, []);

  return (
    <ProfileContext.Provider
      value={{ sessionId, profile, setProfile, clearProfile }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Access the active profile context.
 * Must be used inside a <ProfileProvider> tree.
 */
export function useProfile(): ProfileContextType {
  const ctx = useContext(ProfileContext);
  if (!ctx) {
    throw new Error("useProfile must be used within a ProfileProvider");
  }
  return ctx;
}
