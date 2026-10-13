import { useEffect, useRef } from "react";

import type { IndexJob, IndexStep } from "../api";
import { formatBytes, formatDuration, languageColor, OTHER_COLOR } from "../languages";
import { repoLabel } from "../repoUrl";

interface Props {
  repoUrl: string;
  job: IndexJob | null; // null until the start request returns
  failure: { message: string; cancelled: boolean } | null;
  cancelling: boolean;
  onCancel: () => void;
  onRetry: () => void;
}

const MAX_LANGUAGES = 6;
const LOG_LINES = 8;

export default function IndexingView({ repoUrl, job, failure, cancelling, onCancel, onRetry }: Props) {
  const running = !failure && (job?.status ?? "running") === "running";
  const percent = Math.round((job?.progress ?? 0) * 100);
  const activeStep = job?.steps.find((s) => s.status === "active");

  return (
    <main className="indexing">
      <div className="indexing-inner">
        <header className="indexing-head">
          <div className="indexing-title">
            <p className="eyebrow">
              {failure ? (failure.cancelled ? "Indexing cancelled" : "Indexing failed") : "Indexing repository"}
            </p>
            <h2 className="mono">{repoLabel(repoUrl)}</h2>
          </div>
          {running ? (
            <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={cancelling || !job}>
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={onRetry}>
              Retry
            </button>
          )}
        </header>

        {failure && !failure.cancelled && (
          <div className="indexing-error" role="alert">
            {failure.message}
          </div>
        )}

        <div className="progress-row" aria-live="polite">
          <div
            className={failure ? "progress-track stopped" : "progress-track"}
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Indexing progress"
          >
            <div className="progress-fill" style={{ width: `${percent}%` }} />
          </div>
          <span className="progress-meta mono">
            {percent}% · {formatDuration(job?.elapsed ?? 0)}
          </span>
        </div>
        {running && <p className="progress-caption">{activeStep?.detail ?? activeStep?.label ?? "Starting…"}</p>}

        <ol className="steps">
          {(job?.steps ?? PLACEHOLDER_STEPS).map((step) => (
            <StepRow key={step.key} step={step} />
          ))}
        </ol>

        {job && job.stats.files > 0 && (
          <>
            <dl className="stats">
              <Stat label="Files" value={job.stats.files.toLocaleString()} />
              <Stat label="Folders" value={job.stats.folders.toLocaleString()} />
              <Stat label="Chunks" value={job.stats.chunks ? job.stats.chunks.toLocaleString() : "–"} />
              <Stat label="Size" value={formatBytes(job.stats.bytes)} />
            </dl>
            <LanguageBar languages={job.stats.languages} />
          </>
        )}

        {job && job.log.length > 0 && <ActivityLog lines={job.log} />}
      </div>
    </main>
  );
}

const PLACEHOLDER_STEPS: IndexStep[] = [
  { key: "clone", label: "Clone repository", status: "active", detail: null, duration: null },
  { key: "scan", label: "Scan files", status: "pending", detail: null, duration: null },
  { key: "chunk", label: "Split into chunks", status: "pending", detail: null, duration: null },
  { key: "embed", label: "Embed chunks", status: "pending", detail: null, duration: null },
  { key: "overview", label: "Write overview", status: "pending", detail: null, duration: null },
];

function StepRow({ step }: { step: IndexStep }) {
  return (
    <li className={`step step-${step.status}`}>
      <span className="step-icon" aria-hidden>
        <StepIcon status={step.status} />
      </span>
      <span className="step-label">{step.label}</span>
      <span className="step-detail mono">
        {step.status === "active" && step.detail}
        {step.status !== "active" && step.status !== "pending" && step.duration !== null && formatDuration(step.duration)}
      </span>
    </li>
  );
}

function StepIcon({ status }: { status: IndexStep["status"] }) {
  switch (status) {
    case "done":
      return (
        <svg viewBox="0 0 16 16" width="16" height="16">
          <path d="m4 8.5 2.5 2.5L12 5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "active":
      return <span className="spinner" />;
    case "error":
      return (
        <svg viewBox="0 0 16 16" width="16" height="16">
          <path d="m5 5 6 6M11 5l-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    case "cancelled":
      return (
        <svg viewBox="0 0 16 16" width="16" height="16">
          <path d="M5 8h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    default:
      return <span className="step-dot" />;
  }
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd className="mono">{value}</dd>
    </div>
  );
}

function LanguageBar({ languages }: { languages: IndexJob["stats"]["languages"] }) {
  const total = languages.reduce((sum, l) => sum + l.bytes, 0);
  if (total === 0) return null;
  const top = languages.slice(0, MAX_LANGUAGES);
  const rest = languages.slice(MAX_LANGUAGES).reduce((sum, l) => sum + l.bytes, 0);
  const segments = [
    ...top.map((l) => ({ name: l.name, bytes: l.bytes, color: languageColor(l.name) })),
    ...(rest > 0 ? [{ name: "Other", bytes: rest, color: OTHER_COLOR }] : []),
  ];
  const pct = (bytes: number) => (bytes / total) * 100;

  return (
    <section className="languages" aria-label="Languages">
      <div className="lang-bar">
        {segments.map((s) => (
          <span key={s.name} style={{ width: `${pct(s.bytes)}%`, background: s.color }} title={s.name} />
        ))}
      </div>
      <ul className="lang-legend">
        {segments.map((s) => (
          <li key={s.name}>
            <span className="lang-swatch" style={{ background: s.color }} aria-hidden />
            {s.name} <span className="mono muted">{pct(s.bytes).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ActivityLog({ lines }: { lines: IndexJob["log"] }) {
  const ref = useRef<HTMLOListElement>(null);
  const visible = lines.slice(-LOG_LINES);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [lines.length]);

  return (
    <section className="activity" aria-label="Activity">
      <h3 className="section-title">Activity</h3>
      <ol ref={ref} className="log mono">
        {visible.map((line, i) => (
          <li key={`${line.t}-${i}`}>
            <span className="log-time">+{line.t.toFixed(1)}s</span>
            <span>{line.message}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
