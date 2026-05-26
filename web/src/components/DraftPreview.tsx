export function DraftPreview({ markdown }: { markdown: string }) {
  return (
    <section className="panel draft-panel">
      <div className="panel-heading">
        <span className="eyebrow">Draft Preview</span>
        <h2>草稿预览</h2>
      </div>
      {markdown ? <pre className="draft-content">{markdown}</pre> : <p className="quiet-text">草稿尚未生成。</p>}
    </section>
  );
}
