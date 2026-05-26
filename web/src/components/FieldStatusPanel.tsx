import type { FieldState } from "../app/types";

const sectionTitles: Record<string, string> = {
  A: "文件与项目",
  B: "适用范围",
  C: "焊材与辅助",
  D: "焊接参数",
  E: "热处理温控"
};

export function FieldStatusPanel({ fields }: { fields: Record<string, FieldState> }) {
  const grouped = Object.values(fields).reduce<Record<string, FieldState[]>>((acc, field) => {
    acc[field.section] = [...(acc[field.section] ?? []), field];
    return acc;
  }, {});

  return (
    <section className="panel field-panel">
      <div className="panel-heading">
        <span className="eyebrow">Field State</span>
        <h2>字段状态</h2>
      </div>
      {Object.entries(grouped).map(([section, sectionFields]) => (
        <div className="field-section" key={section}>
          <h3>
            {section}. {sectionTitles[section] ?? section}
          </h3>
          <div className="field-list">
            {sectionFields.map((field) => (
              <div className="field-row" key={field.field_id}>
                <div>
                  <strong>{field.label}</strong>
                  <span>{field.field_id}</span>
                </div>
                <div className="field-value">{field.value === null || field.value === "" ? "未填写" : String(field.value)}</div>
                <span className={`field-status status-${field.status}`}>{field.status}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
