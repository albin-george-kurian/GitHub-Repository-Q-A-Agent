// Colors for the language bar, close to GitHub's linguist palette; very dark ones are lifted so
// they stay visible on the dark theme.
const LANGUAGE_COLORS: Record<string, string> = {
  Python: "#3572a5",
  JavaScript: "#e6c84a",
  TypeScript: "#3178c6",
  Java: "#b07219",
  Go: "#00add8",
  Rust: "#dea584",
  Ruby: "#a33a3a",
  PHP: "#4f5d95",
  "C++": "#f34b7d",
  C: "#7a7a7a",
  "C#": "#178600",
  Kotlin: "#a97bff",
  Swift: "#f05138",
  Scala: "#c22d40",
  Markdown: "#519aba",
  reStructuredText: "#8b949e",
  Text: "#9ca3af",
  JSON: "#cbcb41",
  YAML: "#cb171e",
  TOML: "#9c4221",
  INI: "#94a3b8",
};

export const OTHER_COLOR = "#a1a1aa";

export function languageColor(name: string): string {
  return LANGUAGE_COLORS[name] ?? OTHER_COLOR;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}
