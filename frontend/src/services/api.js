/** API client for backend communication. */

import { API_BASE_URL, API_PREFIX } from "../utils/constants";
import { handleApiError, logError } from "../utils/errorHandler";

/**
 * Generate LiveKit access token.
 * @param {string} userName     - User's display name
 * @param {string} languageCode - BCP-47 language code (e.g. "hi", "ta", "en")
 * @returns {Promise<Object>} Token response with room_name, token, and url
 */
export async function getToken(userName, languageCode = "en") {
  try {
    const params = new URLSearchParams({
      user: userName,
      language: languageCode,
    });

    const response = await fetch(
      `${API_BASE_URL}${API_PREFIX}/auth/connect?${params.toString()}`,
      {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const error = new Error(
        errorData.error || `HTTP error! status: ${response.status}`
      );
      error.response = { status: response.status, data: errorData };
      throw error;
    }

    return await response.json();
  } catch (error) {
    logError(error, "getToken");
    throw error;
  }
}

/**
 * Health check endpoint.
 * @returns {Promise<Object>} Health status
 */
export async function healthCheck() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
    });

    if (!response.ok) {
      throw new Error(`Health check failed: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    logError(error, "healthCheck");
    throw error;
  }
}