export function EvidenceDrawer({ report }: { report: Record<string, unknown> }) {
  const risks = Array.isArray(report.risks) ? report.risks : [];

  return (
    <section className="panel evidence-panel">
      <div className="panel-heading">
        <span className="eyebrow">Evidence And Risk</span>
        <h2>证据与风险</h2>
      </div>
      {risks.length ? (
        <div className="risk-list">
          {risks.slice(0, 8).map((risk, index) => (
            <pre className="risk-item" key={index}>
              {JSON.stringify(risk, null, 2)}
            </pre>
          ))}
        </div>
      ) : (
        <p className="quiet-text">暂无风险条目。</p>
      )}
    </section>
  );
}
