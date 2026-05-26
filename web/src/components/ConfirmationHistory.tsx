export function ConfirmationHistory({ confirmations }: { confirmations: Array<Record<string, unknown>> }) {
  return (
    <section className="panel history-panel">
      <div className="panel-heading">
        <span className="eyebrow">Confirmations</span>
        <h2>确认记录</h2>
      </div>
      {confirmations.length ? (
        <div className="history-list">
          {confirmations.map((record, index) => (
            <div className="history-item" key={String(record.confirmation_id ?? index)}>
              <strong>{String(record.confirmation_id ?? `confirm_${index + 1}`)}</strong>
              <span>{String(record.action ?? "action")}</span>
              <p>{Array.isArray(record.field_ids) ? record.field_ids.join(", ") : ""}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="quiet-text">暂无人工确认。</p>
      )}
    </section>
  );
}
