import { BASE_URL, makeCommonAxios, getErrMsg } from './common';

const API_PREFIX_PATH = "itineraries"

export interface ListItinerariesResponse {
  itineraries?: any[]
  error?: string
}

export const listItineraries = async (authToken: string): Promise<ListItinerariesResponse> => {
  return makeCommonAxios().get(`${BASE_URL}/${API_PREFIX_PATH}`, {
    headers: {
      Authorization: `Bearer ${authToken}`
    }
  })
    .then(res => {
      return { itineraries: res.data };
    })
    .catch((err) => {
      return { error: getErrMsg(err) };
    });
}

/**
 * Shared helper to parse SSE chunks and dispatch events
 */
const handleSSE = async (response: Response, onChunk?: Function, onComplete?: Function) => {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    const parts = buffer.split('\n\n');

    // The last part might be incomplete
    buffer = parts.pop() || '';

    for (const part of parts) {
      let eventType = 'message';
      let dataLine = '';

      for (const line of part.split('\n')) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim();
        if (line.startsWith('data:')) dataLine = line.slice(5).trim();
      }

      if (!dataLine) continue;

      let parsed;
      try {
        parsed = JSON.parse(dataLine);
      } catch {
        continue;
      }

      if (eventType === 'complete') {
        if (onComplete) onComplete(parsed);
      } else {
        if (onChunk) onChunk(eventType, parsed);
      }
    }
  }
};

export interface StreamPlanPayload {
  user_input: string;
  mode: string;
  booking_mode: string;
  thread_id?: string | null;
}

/**
 * Initiates Pass 1 streaming (Planning, Options generation)
 */
export const streamPlan = async (
  payload: StreamPlanPayload,
  authToken: string | undefined,
  onChunk: (type: string, data: any) => void,
  onComplete: (data: any) => void,
  signal?: AbortSignal
) => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${BASE_URL}/plan/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }

  await handleSSE(response, onChunk, onComplete);
};

/**
 * Initiates Pass 2 streaming (Confirming selections and returning itinerary)
 */
export const streamPass2 = async (
  planId: string,
  payload: any,
  authToken: string | undefined,
  onChunk: (type: string, data: any) => void,
  onComplete: (data: any) => void,
  signal?: AbortSignal
) => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${BASE_URL}/plan/${planId}/select`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }

  await handleSSE(response, onChunk, onComplete);
};

/**
 * Initiates Pass 2 Stage B (Confirm meal selections, run Day Planner)
 */
export const streamMeals = async (
  planId: string,
  payload: { selected_meals: any[]; auto_select: boolean },
  authToken: string | undefined,
  onChunk: (type: string, data: any) => void,
  onComplete: (data: any) => void,
  signal?: AbortSignal
) => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${BASE_URL}/plan/${planId}/meals`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }

  await handleSSE(response, onChunk, onComplete);
};

/**
 * Edit an existing itinerary with a natural language instruction
 */
export const editItinerary = async (
  planId: string,
  editText: string,
  threadId: string,
  authToken: string | undefined,
): Promise<any> => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${BASE_URL}/plan/${planId}/edit`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ edit_text: editText, thread_id: threadId }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }

  return response.json();
};

/**
 * Confirm an itinerary with chosen booking mode
 */
export const confirmPlan = async (
  planId: string,
  bookingMode: 'search_recommend' | 'sandbox',
  authToken: string | undefined,
): Promise<any> => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${BASE_URL}/plan/${planId}/confirm`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ booking_mode: bookingMode }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }

  return response.json();
};

export const getItinerary = async (id: string, authToken: string): Promise<any> => {
  return makeCommonAxios().get(`${BASE_URL}/${API_PREFIX_PATH}/${id}`, {
    headers: {
      Authorization: `Bearer ${authToken}`
    }
  })
    .then(res => res.data)
    .catch((err) => {
      return { error: getErrMsg(err) };
    });
}

const API = {
  listItineraries,
  getItinerary,
  streamPlan,
  streamPass2,
  streamMeals,
  editItinerary,
  confirmPlan,
};

export default API;
