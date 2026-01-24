/** Error handling utilities. */

import { ERROR_MESSAGES } from "./constants";

/**
 * Handle API errors and return user-friendly messages.
 * @param {Error} error - The error object
 * @returns {string} User-friendly error message
 */
export function handleApiError(error) {
  if (error instanceof TypeError && error.message.includes("fetch")) {
    return ERROR_MESSAGES.NETWORK_ERROR;
  }

  if (error.response) {
    // API error response
    const status = error.response.status;
    if (status === 429) {
      return "Too many requests. Please wait a moment and try again.";
    }
    if (status >= 500) {
      return "Server error. Please try again later.";
    }
    if (status === 401 || status === 403) {
      return "Authentication failed. Please refresh and try again.";
    }
    return error.response.data?.error || error.response.data?.detail || ERROR_MESSAGES.UNKNOWN_ERROR;
  }

  if (error.message) {
    return error.message;
  }

  return ERROR_MESSAGES.UNKNOWN_ERROR;
}

/**
 * Log error for debugging.
 * @param {Error} error - The error object
 * @param {string} context - Context where error occurred
 */
export function logError(error, context = "Unknown") {
  if (import.meta.env.DEV) {
    console.error(`[${context}]`, error);
  }
  // In production, you might want to send to error tracking service
}

