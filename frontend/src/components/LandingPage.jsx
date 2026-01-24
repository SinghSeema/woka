/** Landing page component. */

import React, { useState } from "react";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { APP_NAME } from "../utils/constants";
import { handleApiError } from "../utils/errorHandler";

/**
 * Landing page component.
 * @param {Object} props - Component props
 * @param {Function} props.onConnect - Callback when user connects
 */
export function LandingPage({ onConnect }) {
  const [userName, setUserName] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!userName.trim()) {
      setError("Please enter your name");
      return;
    }

    setIsConnecting(true);
    setError(null);

    try {
      await onConnect(userName.trim());
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 via-emerald-50 to-teal-50 flex items-center justify-center p-4">
      <Card className="max-w-md w-full p-8 md:p-10">
        <div className="text-center mb-8">
          <div className="text-6xl mb-4">🌿</div>
          <h1 className="text-3xl md:text-4xl font-bold text-gray-800 mb-2">
            {APP_NAME}
          </h1>
          <p className="text-gray-600 text-lg">
            Your AI-powered guide to habit formation, sleep, and mindfulness.
          </p>
        </div>

        <div className="space-y-3 mb-8">
          <div className="flex items-center text-gray-700">
            <span className="text-green-600 mr-2">✓</span>
            <span>Personalized Coaching</span>
          </div>
          <div className="flex items-center text-gray-700">
            <span className="text-green-600 mr-2">✓</span>
            <span>Real-time Support</span>
          </div>
          <div className="flex items-center text-gray-700">
            <span className="text-green-600 mr-2">✓</span>
            <span>Voice-Activated Sessions</span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="text"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              placeholder="Enter your name"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
              disabled={isConnecting}
              autoFocus
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <Button
            type="submit"
            variant="primary"
            size="lg"
            disabled={isConnecting}
            className="w-full"
          >
            {isConnecting ? "Connecting..." : "Start Coaching Session"}
          </Button>
        </form>

        <p className="text-xs text-gray-500 text-center mt-6">
          Always consult a medical professional for health concerns.
        </p>
      </Card>
    </div>
  );
}

