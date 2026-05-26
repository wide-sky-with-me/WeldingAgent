export function EventTimeline({ trace }: { trace: Array<Record<string, unknown>> }) {
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <span className="eyebrow">Runtime</span>
        <h2>运行过程</h2>
      </div>
      <div className="timeline-list">
        {trace.slice(-12).map((event, index) => (
          <div className="timeline-item" key={`${String(event.step ?? index)}-${index}`}>
            <span>{String(event.node ?? "node")}</span>
            <strong>{String(event.event_type ?? "event")}</strong>
            <p>{String(event.summary ?? "")}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
