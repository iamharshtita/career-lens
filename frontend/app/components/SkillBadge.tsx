/**
 * SkillBadge — pill-shaped tag for a single skill.
 */

interface SkillBadgeProps {
  skill: string;
}

export default function SkillBadge({ skill }: SkillBadgeProps) {
  return (
    <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-0.5 text-sm font-medium text-blue-800">
      {skill}
    </span>
  );
}
