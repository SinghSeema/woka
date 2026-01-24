/** Error boundary hook for React components. */

import { useState, useEffect } from "react";

/**
 * Custom hook for error boundary functionality.
 * @returns {Object} Error state and reset function
 */
export function useErrorBoundary() {
  const [error, setError] = useState(null);

  useEffect(() => {
    if (error) {
      // Log error
      console.error("Error boundary caught:", error);
    }
  }, [error]);

  const resetError = () => {
    setError(null);
  };

  return { error, setError, resetError };
}

