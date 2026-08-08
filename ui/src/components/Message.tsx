import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types";
import { GroundingTrace } from "./GroundingTrace";

/**
 * One chat row. User turns render as plain text; assistant turns render the
 * model's Markdown (GFM tables included) and, when present, the grounding panel.
 */
export function MessageView({ msg }: { msg: Message }) {
  const isYou = msg.role === "you";
  const bubbleClass =
    "bubble" + (isYou ? "" : " md") + (msg.error ? " err" : "");

  return (
    <div className={"msg " + (isYou ? "you" : "bot")}>
      <div className="role">{isYou ? "you" : "assistant"}</div>
      <div className={bubbleClass}>
        {msg.pending ? (
          <span className="dots" />
        ) : isYou ? (
          msg.text
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
        )}
      </div>
      {!isYou && msg.trace && <GroundingTrace trace={msg.trace} />}
    </div>
  );
}
