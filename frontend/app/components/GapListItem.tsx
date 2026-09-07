/**
 * GapListItem — renders one ranked skill gap with a criticality badge.
 */

import type { SkillGap } from "../context/ProfileContext";

interface GapListItemProps {
  gap: SkillGap;
  rank: number;
}

const CRITICALITY_STYLES: Record<SkillGap["criticality"], string> = {
  critical: "bg-red-100 text-red-700",
  important: "bg-orange-100 text-orange-700",
  "nice-to-have": "bg-gray-100 text-gray-600",
};

const CRITICALITY_LABELS: Record<SkillGap["criticality"], string> = {
  critical: "Critical",
  important: "Important",
  "nice-to-have": "Nice to have",
};

export default function GapListItem({ gap, rank }: GapListItemProps) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
      {/* Rank number */}
      <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
        {rank}
      </span>

      {/* Skill name */}
      <span className="flex-1 text-sm font-medium text-gray-800">
        {gap.skill}
      </span>

      {/* Criticality badge */}
      <span
        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${CRITICALITY_STYLES[gap.criticality]}`}
      >
        {CRITICALITY_LABELS[gap.criticality]}
      </span>
    </li>
  );
}
