import { Send } from "lucide-react";
import { useState } from "react";
import type { InteractionRequest } from "../app/types";

export function InteractionPanel({
  interaction,
  onRespond
}: {
  interaction: InteractionRequest | null;
  onRespond: (message: string) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(nextMessage = message) {
    if (!nextMessage.trim()) return;
    setSubmitting(true);
    try {
      await onRespond(nextMessage.trim());
      setMessage("");
    } finally {
      setSubmitting(false);
    }
  }

  if (!interaction) {
    return (
      <section className="panel primary-panel">
        <div className="panel-heading">
          <span className="eyebrow">Current Interaction</span>
          <h2>当前无需用户输入</h2>
        </div>
        <p className="quiet-text">运行没有停在交互节点。可以查看字段、草稿和事件记录。</p>
      </section>
    );
  }

  return (
    <section className="panel primary-panel">
      <div className="panel-heading">
        <span className="eyebrow">Current Interaction</span>
        <h2>{interaction.title}</h2>
      </div>
      <p className="summary-text">{interaction.summary}</p>
      {interaction.assistant_message ? (
        <div className="assistant-message">{interaction.assistant_message}</div>
      ) : null}
      <div className="question-stack">
        {interaction.questions.map((question) => (
          <div className="question-block" key={question.question_id}>
            <div className="question-title">
              <h3>{question.prompt}</h3>
              <span>{question.field_ids.join(", ")}</span>
            </div>
            {question.options.length ? (
              <div className="option-grid">
                {question.options.map((option, index) => (
                  <button
                    className={option.recommended ? "option-button recommended" : "option-button"}
                    key={`${question.question_id}-${index}`}
                    type="button"
                    onClick={() => setMessage(String(index + 1))}
                  >
                    <span className="option-index">{index + 1}</span>
                    <span className="option-main">{String(option.label ?? option.value)}</span>
                    {option.recommended ? <span className="recommend-badge">推荐</span> : null}
                    {option.suitability ? <span className="option-note">适用性: {option.suitability}</span> : null}
                    {option.risk_note ? <span className="option-risk">风险: {option.risk_note}</span> : null}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <textarea
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="输入编号、field=value，或直接用自然语言补充。"
      />
      <button className="submit-button" type="button" onClick={() => submit()} disabled={submitting}>
        <Send size={16} />
        提交并继续
      </button>
    </section>
  );
}
