// Central axios instance so we can control the API base URL.
// Precedence: window.__ENV__ (runtime injected) > build-time env var > ''
import axios from 'axios';

// Runtime override (e.g., served with an injected /env-config.js produced at container start)
const runtime = (typeof window !== 'undefined' && window.__ENV__ && window.__ENV__.REACT_APP_API_BASE_URL) || undefined;
const buildTime = process.env.REACT_APP_API_BASE_URL;

// Treat placeholder or empty values as invalid so we gracefully fallback to '/api'
const invalidValues = [undefined, null, '', '__MISSING__'];
const picked = !invalidValues.includes(runtime) ? runtime : (!invalidValues.includes(buildTime) ? buildTime : undefined);

// Default fallback to '/api' so that code can just call endpoints like '/books'
const baseURL = picked || '/api';

const api = axios.create({
  baseURL,
});

export default api;
