// src/lib/api.js

export const API_BASE = "http://localhost:8000";

export async function login(username, password) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.message || "Login failed");
  }
  return response.json();
}

export async function register(username, password) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.message || "Registration failed");
  }
  return response.json();
}

export async function syncHistory(userId, threadId, messages) {
  const cleanMessages = messages.map(({ role, content }) =>({role, content}));
  const response = await fetch(`${API_BASE}/user/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      user_id: userId, 
      thread_id: threadId, 
      messages: cleanMessages 
    }),
  });
  if (!response.ok) throw new Error("Failed to sync history");
  return response.json();
}

export async function getHistory(userId) {
  const response = await fetch(`${API_BASE}/user/history/${userId}`);
  if (!response.ok) throw new Error("Failed to fetch history");
  return response.json();
}

export async function startTask(query, userId) {
  const response = await fetch(`${API_BASE}/research/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, user_id: userId }),
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
