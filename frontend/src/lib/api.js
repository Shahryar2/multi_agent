// src/lib/api.js

export const API_BASE = "http://localhost:8000";

export async function startTask(query) {
  const response = await fetch(`${API_BASE}/research/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error("Failed to start task");
  return response.json();
}

export async function approvePlan(threadId, plan) {
  const response = await fetch(`${API_BASE}/research/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, plan }),
  });
  if (!response.ok) throw new Error("Failed to approve plan");
  return response.json();
}
