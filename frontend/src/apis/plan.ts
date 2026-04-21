const getApiBase = () => {
  return import.meta.env.VITE_API_URL || 'http://localhost:8000';
};

/**
 * Shared helper to parse SSE chunks and dispatch events
 */
const handleSSE = async (response, onChunk, onComplete) => {
  const reader = response.body.getReader();
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

/**
 * Initiates Pass 1 streaming (Planning, Options generation)
 */
export const streamPlan = async (payload, authToken, onChunk, onComplete, signal) => {
  const apiBase = getApiBase();
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${apiBase}/plan/stream`, {
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
export const streamPass2 = async (planId, payload, authToken, onChunk, onComplete, signal) => {
  const apiBase = getApiBase();
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${apiBase}/plan/${planId}/select`, {
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
 * Confirm a booking once an itinerary has been finalized
 */
export const confirmBooking = async (planId, authToken) => {
  const apiBase = getApiBase();
  const headers = {};
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const res = await fetch(`${apiBase}/plan/${planId}/confirm`, {
    method: 'POST',
    headers
  });

  if (res.status === 409) {
    const body = await res.json();
    return { alreadyConfirmed: true, ...body };
  }
  
  if (!res.ok) {
    throw new Error(`Confirm failed: ${res.status}`);
  }
  
  return res.json();
};
