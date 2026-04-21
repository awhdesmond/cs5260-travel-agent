const getApiBase = () => {
  return import.meta.env.VITE_API_URL || 'http://localhost:8000';
};

export const exportMetrics = async (format, authToken) => {
  const apiBase = getApiBase();
  const res = await fetch(`${apiBase}/metrics/export?format=${format}`, {
    headers: { 'Authorization': `Bearer ${authToken}` }
  });
  
  if (!res.ok) {
    throw new Error(`Export failed: ${res.status}`);
  }
  
  if (format === 'csv') {
    return res.blob();
  }
  return res.json();
};
