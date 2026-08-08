import type { TraceStep } from "../types";

/**
 * The grounding panel: shows which deterministic tools ran and the source row
 * IDs each returned. Generated from the backend trace (not the model), so it is
 * the auditable record of how an answer was computed.
 */
export function GroundingTrace({ trace }: { trace: TraceStep[] }) {
  if (!trace.length) return null;
  return (
    <div className="trace">
      <span className="trace-label">How this was computed: </span>
      {trace.map((step, i) => (
        <span key={i} className="trace-step">
          {i > 0 && <span className="sep"> · </span>}
          <b>{step.tool}</b>
          {step.sources.length > 0 && <span> → </span>}
          {step.sources.slice(0, 8).map((s) => (
            <code key={s}>{s}</code>
          ))}
          {step.sources.length > 8 && <span> …</span>}
        </span>
      ))}
    </div>
  );
}
