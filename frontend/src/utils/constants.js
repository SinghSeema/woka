/** Application constants. */

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const API_PREFIX = import.meta.env.VITE_API_PREFIX || "/api/v1";

export const APP_NAME = "Woka Wellness";
export const APP_VERSION = "1.0.0";

export const BOT_NAME = "Woka";

export const ERROR_MESSAGES = {
  CONNECTION_FAILED: "Failed to connect to the server. Please try again.",
  INVALID_USERNAME: "Please enter a valid name.",
  NETWORK_ERROR: "Network error. Please check your connection.",
  UNKNOWN_ERROR: "An unexpected error occurred. Please try again.",
};

export const SUCCESS_MESSAGES = {
  CONNECTED: "Successfully connected to the session.",
};

