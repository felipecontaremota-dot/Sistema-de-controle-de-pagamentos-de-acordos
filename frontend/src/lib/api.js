import axios from "axios";

const BACKEND_URL = (process.env.REACT_APP_API_URL || "https://legacord-backend.onrender.com")
  .replace(/\/$/, "");

export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
});
