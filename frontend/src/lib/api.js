// src/lib/api.js

export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function getErrorMessage(response, fallback) {
  try {
    const err = await response.json();
    return err.detail || err.message || fallback;
  } catch {
    return fallback;
  }
}

function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function login(username, password) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response, "Login failed"));
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
    throw new Error(await getErrorMessage(response, "Registration failed"));
  }
  return response.json();
}

export async function syncHistory(userId, threadId, messages, token) {
  const cleanMessages = messages.map(({ role, content }) =>({role, content}));
  const response = await fetch(`${API_BASE}/user/sync`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ user_id: userId, thread_id: threadId, messages: cleanMessages }),
  });
  if (!response.ok) throw new Error("Failed to sync history");
  return response.json();
}

export async function getHistory(userId, token) {
  const response = await fetch(`${API_BASE}/user/history/${userId}`, {
    headers: authHeaders(token),
  });
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to fetch history"));
  return response.json();
}

export async function toggleFavorite(userId, threadId, token) {
  const response = await fetch(`${API_BASE}/user/favorite`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ user_id: userId, thread_id: threadId }),
  });
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to toggle favorite"));
  return response.json();
}

export async function deleteHistory(userId, threadId, token) {
  const response = await fetch(`${API_BASE}/user/history/${userId}/${threadId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to delete history"));
  return response.json();
}

export async function startTask(query, userId, mode = "research") {
  const response = await fetch(`${API_BASE}/research/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      query, 
      user_id: userId,
      mode,  // ✅ 新增：传递模式
    }),
  });
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to start task"));
  return response.json();
}

export async function continueTask(threadId, query, userId, mode) {
  const response = await fetch(`${API_BASE}/research/${threadId}/continue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, user_id: userId, mode }),
  });
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to continue task"));
  return response.json();
}

export async function stopTask(threadId) {
  const response = await fetch(`${API_BASE}/research/${threadId}/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to stop task"));
  return response.json();
}

export async function approvePlan(threadId, plan) {
  const response = await fetch(`${API_BASE}/research/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, plan }),
  });
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to approve plan"));
  return response.json();
}


export async function getTaskState(threadId) {
  const response = await fetch(`${API_BASE}/research/${threadId}/state`);
  if (!response.ok) throw new Error(await getErrorMessage(response, "Failed to fetch task state"));
  return response.json();
}