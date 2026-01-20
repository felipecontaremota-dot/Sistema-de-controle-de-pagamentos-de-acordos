import axios from "axios";

const BACKEND_URL = (
  process.env.REACT_APP_API_URL ||
  "https://legacord-backend.onrender.com"
).replace(/\/$/, "");

export const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API_BASE,
});

// ---------------------------------------------
//  ADICIONAR TOKEN AUTOMATICAMENTE
// ---------------------------------------------
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ---------------------------------------------
//  TRATAR ERRO 401 AUTOMATICAMENTE
// ---------------------------------------------
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
