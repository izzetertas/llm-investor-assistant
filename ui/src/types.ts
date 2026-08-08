export interface Investor {
  id: string;
  name: string;
  reporting_currency: string;
}

export interface TraceStep {
  tool: string;
  args: Record<string, unknown>;
  sources: string[];
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  trace: TraceStep[];
}

export interface Message {
  role: "you" | "bot";
  text: string;
  trace?: TraceStep[];
  pending?: boolean;
  error?: boolean;
}
