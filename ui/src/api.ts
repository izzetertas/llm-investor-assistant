import type { ChatResponse, Investor } from "./types";

export async function fetchInvestors(): Promise<Investor[]> {
  const res = await fetch("/api/investors");
  if (!res.ok) throw new Error("Failed to load investors");
  return res.json();
}

export async function sendChat(params: {
  investorId: string;
  message: string;
  sessionId: string | null;
}): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      investor_id: params.investorId,
      message: params.message,
      session_id: params.sessionId,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error((data && data.detail) || `Request failed (${res.status})`);
  }
  return data as ChatResponse;
}
