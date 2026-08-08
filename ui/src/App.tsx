import { useEffect, useRef, useState } from "react";
import { fetchInvestors, sendChat } from "./api";
import type { Investor, Message } from "./types";
import { MessageView } from "./components/Message";
import { Composer } from "./components/Composer";
import "./styles.css";

const EXAMPLES = [
  "What's my portfolio worth and what's my MOIC?",
  "Show me my Forgecraft position across rounds.",
  "Any overdue fees or upcoming capital calls?",
  "What fees am I paying on Inferna — did I get a discount?",
];

export default function App() {
  const [investors, setInvestors] = useState<Investor[]>([]);
  const [investorId, setInvestorId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const mainRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchInvestors()
      .then((list) => {
        setInvestors(list);
        setInvestorId(list[0]?.id ?? "");
      })
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    mainRef.current?.scrollTo({ top: mainRef.current.scrollHeight });
  }, [messages]);

  const currency =
    investors.find((i) => i.id === investorId)?.reporting_currency ?? "—";

  function changeInvestor(id: string) {
    setInvestorId(id);
    setSessionId(null); // new investor -> fresh session
    setMessages([]);
  }

  async function handleSend(text: string) {
    setMessages((m) => [...m, { role: "you", text }, { role: "bot", text: "", pending: true }]);
    setLoading(true);
    try {
      const data = await sendChat({ investorId, message: text, sessionId });
      setSessionId(data.session_id);
      setMessages((m) => replaceLast(m, { role: "bot", text: data.answer, trace: data.trace }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((m) => replaceLast(m, { role: "bot", text: "⚠ " + msg, error: true }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>
          Investor<span>Assistant</span>
        </h1>
        <div className="who">
          <label htmlFor="investor">Logged in as</label>
          <select
            id="investor"
            value={investorId}
            onChange={(e) => changeInvestor(e.target.value)}
          >
            {investors.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {inv.name} ({inv.id})
              </option>
            ))}
          </select>
          <span className="badge">{currency}</span>
        </div>
      </header>

      <main ref={mainRef}>
        {loadError && (
          <div className="msg bot">
            <div className="bubble err">⚠ {loadError}</div>
          </div>
        )}

        {messages.length === 0 && !loadError && (
          <div className="msg bot">
            <div className="role">assistant</div>
            <div className="bubble hint">
              Ask about <b>your own</b> portfolio — holdings, valuations, MOIC,
              fees, capital calls, distributions, or your statement. Every figure
              is computed from the data and cited to its source rows.
              <div className="examples">
                {EXAMPLES.map((q) => (
                  <button key={q} onClick={() => handleSend(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <MessageView key={i} msg={m} />
        ))}
      </main>

      <footer>
        <Composer disabled={loading || !investorId} onSend={handleSend} />
      </footer>
    </div>
  );
}

function replaceLast(list: Message[], msg: Message): Message[] {
  const copy = [...list];
  copy[copy.length - 1] = msg;
  return copy;
}
