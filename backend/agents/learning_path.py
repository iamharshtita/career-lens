"""
Learning Path Agent — CareerLens

Builds a personalised learning path for every skill gap returned by the
Gap Analyzer Agent. For each SkillGap the agent queries:

  * YouTube Data API v3 (up to 3 videos per skill)
  * Coursera public catalog API v1 (up to 2 courses per skill)

Results are mapped into VideoResource / CourseResource objects and
assembled into a list[LearningStep] whose `priority` fields mirror the
corresponding SkillGap.rank values.

All API errors and empty-result responses are handled silently — the
function never raises on a per-skill failure; it simply returns an empty
resource list for that skill.

Required environment variable
------------------------------
YOUTUBE_API_KEY   — Google Data API key with YouTube Data API v3 enabled.
                    A ValueError is raised at module import time if the
                    variable is absent so the problem surfaces at startup,
                    not mid-request.

Optional environment variable
------------------------------
CAREERLENS_DATA_DIR  — not used here (handled by the storage layer).
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

import html
import httpx

from models.schemas import (
    CourseResource,
    LearningStep,
    SkillGap,
    VideoResource,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration & validation
# ---------------------------------------------------------------------------

YOUTUBE_API_KEY: str = os.environ.get("YOUTUBE_API_KEY", "")
if not YOUTUBE_API_KEY:
    raise ValueError(
        "YOUTUBE_API_KEY environment variable is not set. "
        "Add it to your .env file or export it before starting the server."
    )

# API endpoints
_YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_COURSERA_SEARCH_URL = "https://api.coursera.org/api/courses.v1"

# HTTP timeouts (seconds)
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_youtube_resources(skill: str, client: httpx.Client) -> list[VideoResource]:
    """Query YouTube Data API v3 and return up to 3 VideoResource objects.

    Returns an empty list on any error or empty response.
    """
    # Append "tutorial" to disambiguate skills like "Dart" (language vs sport)
    search_query = f"{skill} tutorial"
    params = {
        "q": search_query,
        "type": "video",
        "part": "snippet",
        "maxResults": 3,
        "key": YOUTUBE_API_KEY,
        "relevanceLanguage": "en",
        "videoCategoryId": "27",  # Education category
    }
    try:
        response = client.get(_YT_SEARCH_URL, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("YouTube API call failed for skill %r: %s", skill, exc)
        return []

    resources: list[VideoResource] = []
    for item in data.get("items", []):
        try:
            snippet = item["snippet"]
            video_id = item["id"]["videoId"]
            resources.append(
                VideoResource(
                    title=html.unescape(snippet.get("title", "")),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    channel=snippet.get("channelTitle", ""),
                    duration_seconds=None,  # requires a separate Videos.list call
                )
            )
        except (KeyError, TypeError) as exc:
            logger.debug("Skipping malformed YouTube item: %s", exc)
            continue

    return resources


def _fetch_coursera_resources(skill: str, client: httpx.Client) -> list[CourseResource]:
    """Return Coursera search links for a skill.

    The Coursera public API no longer supports unauthenticated access, so
    we return a pre-built search URL pointing to the Coursera catalog.
    This always works and gives the user a useful link to explore courses.
    """
    from urllib.parse import quote_plus as _qp
    search_url = f"https://www.coursera.org/search?query={_qp(skill)}"
    return [
        CourseResource(
            title=f"Search Coursera for \"{skill}\" courses",
            url=search_url,
            provider="Coursera",
            duration_weeks=None,
        )
    ]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def build_learning_path(skill_gaps: list[SkillGap]) -> list[LearningStep]:
    """Build a personalised learning path from a ranked list of skill gaps.

    For each SkillGap the function queries YouTube and Coursera, then
    assembles the results into a LearningStep whose `priority` mirrors the
    gap's `rank`.  The returned list preserves the input order, so
    ``learning_path[i].priority == skill_gaps[i].rank`` for all valid
    indices (Property 9).

    Parameters
    ----------
    skill_gaps:
        Ordered list of SkillGap objects (rank 1 = highest priority).
        An empty list is valid and returns an empty learning path.

    Returns
    -------
    list[LearningStep]
        One LearningStep per input gap, in the same order.  Resource
        lists are empty when the relevant API returned no results.
    """
    if not skill_gaps:
        return []

    learning_path: list[LearningStep] = []

    # Re-use a single connection pool for all requests in this batch.
    with httpx.Client() as client:
        for gap in skill_gaps:
            skill = gap.skill

            youtube_resources = _fetch_youtube_resources(skill, client)
            coursera_resources = _fetch_coursera_resources(skill, client)

            step = LearningStep(
                skill_gap=skill,
                priority=gap.rank,
                youtube_resources=youtube_resources,
                coursera_resources=coursera_resources,
            )
            learning_path.append(step)

    return learning_path
