/** Room view component for active voice session - Enhanced with Woka branding. */

import React from "react";
import {
  LiveKitRoom,
  ParticipantTile,
  RoomAudioRenderer,
  useTracks,
  useParticipants,
  useLocalParticipant,
  useRoomContext,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { Track } from "livekit-client";
import { BOT_NAME } from "../utils/constants";

/**
 * Zoom-style Audio Control Bar Component
 */
function ZoomControlBar({ onDisconnect }) {
  const { localParticipant } = useLocalParticipant();
  const room = useRoomContext();
  const [isMuted, setIsMuted] = React.useState(false);

  React.useEffect(() => {
    if (localParticipant && localParticipant.audioTracks) {
      // Check initial mute state
      const audioTrackEntries = Array.from(localParticipant.audioTracks.values());
      const audioTrack = audioTrackEntries.length > 0 ? audioTrackEntries[0]?.track : null;
      
      if (audioTrack) {
        setIsMuted(audioTrack.isMuted);
        
        // Listen for mute state changes
        const handleMuteChange = () => {
          setIsMuted(audioTrack.isMuted);
        };
        
        audioTrack.on("muted", handleMuteChange);
        audioTrack.on("unmuted", handleMuteChange);
        
        return () => {
          audioTrack.off("muted", handleMuteChange);
          audioTrack.off("unmuted", handleMuteChange);
        };
      } else {
        // If no track, check microphone enabled state
        setIsMuted(!localParticipant.isMicrophoneEnabled);
      }
    }
  }, [localParticipant]);

  const handleToggleMute = async () => {
    if (!localParticipant) return;
    
    try {
      // Check if audioTracks exists and has entries
      if (localParticipant.audioTracks && localParticipant.audioTracks.size > 0) {
        const audioTrackEntries = Array.from(localParticipant.audioTracks.values());
        const audioTrack = audioTrackEntries[0]?.track;
        
        if (audioTrack) {
          if (audioTrack.isMuted) {
            await audioTrack.unmute();
          } else {
            await audioTrack.mute();
          }
          return;
        }
      }
      
      // Fallback: toggle microphone enabled state
      const isEnabled = localParticipant.isMicrophoneEnabled ?? true;
      await localParticipant.setMicrophoneEnabled(!isEnabled);
      setIsMuted(isEnabled);
    } catch (error) {
      console.error("Error toggling mute:", error);
    }
  };

  const handleDisconnect = async () => {
    try {
      if (room) {
        await room.disconnect();
      }
      if (onDisconnect) {
        onDisconnect();
      }
    } catch (error) {
      console.error("Error disconnecting:", error);
      // Still call onDisconnect even if room disconnect fails
      if (onDisconnect) {
        onDisconnect();
      }
    }
  };

  return (
    <div className="bg-[#1a1a1a] border-t border-gray-800 px-4 md:px-6 py-5">
      <div className="flex justify-center items-center gap-6">
        {/* Mute/Unmute Button - Zoom style */}
        <button
          onClick={handleToggleMute}
          className={`group relative w-14 h-14 md:w-16 md:h-16 rounded-full flex items-center justify-center transition-all duration-200 shadow-xl hover:scale-110 ${
            isMuted
              ? "bg-red-600 hover:bg-red-700 text-white ring-4 ring-red-600/30"
              : "bg-gray-700 hover:bg-gray-600 text-white ring-4 ring-gray-700/30"
          }`}
          aria-label={isMuted ? "Unmute" : "Mute"}
        >
          {isMuted ? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-7 h-7 md:w-8 md:h-8"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5 5l14 14"
              />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-7 h-7 md:w-8 md:h-8"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
          )}
          {/* Tooltip */}
          <span className="absolute -top-12 left-1/2 transform -translate-x-1/2 bg-black/80 text-white text-xs px-3 py-1.5 rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
            {isMuted ? "Unmute" : "Mute"}
          </span>
        </button>

        {/* Disconnect Button - Red Round (Zoom style) */}
        <button
          onClick={handleDisconnect}
          className="group relative w-14 h-14 md:w-16 md:h-16 rounded-full bg-red-600 hover:bg-red-700 text-white flex items-center justify-center transition-all duration-200 shadow-xl hover:scale-110 ring-4 ring-red-600/30"
          aria-label="Leave call"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-7 h-7 md:w-8 md:h-8"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={3}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
          {/* Tooltip */}
          <span className="absolute -top-12 left-1/2 transform -translate-x-1/2 bg-black/80 text-white text-xs px-3 py-1.5 rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
            Leave
          </span>
        </button>
      </div>
    </div>
  );
}

/**
 * Participant Avatar Component - Logo-style avatars (no external images needed)
 */
function ParticipantAvatar({ 
  name, 
  isBot = false, 
  isActive = false 
}) {
  // Get initials for user
  const initials = isBot ? "W" : name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  
  return (
    <div className="relative w-full h-full flex items-center justify-center bg-gray-900 rounded-lg overflow-hidden">
      {/* Background gradient */}
      {isBot ? (
        <div
          className={`absolute inset-0 bg-gradient-to-br from-green-500 via-emerald-600 to-teal-600 ${
            isActive ? "animate-pulse" : ""
          }`}
        />
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-600" />
      )}
      
      {/* Avatar Logo Circle */}
      <div className="relative z-10 flex flex-col items-center justify-center w-full h-full">
        <div className={`w-48 h-48 md:w-56 md:h-56 rounded-full flex items-center justify-center shadow-2xl border-4 ${
          isBot 
            ? "bg-white/10 backdrop-blur-sm border-white/30" 
            : "bg-white/10 backdrop-blur-sm border-white/30"
        }`}>
          {isBot ? (
            // Woka Logo - Large emoji/icon
            <div className="text-8xl md:text-9xl">🌿</div>
          ) : (
            // User Logo - Initials in a styled circle
            <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full">
              <span className="text-5xl md:text-6xl font-bold text-white">{initials}</span>
            </div>
          )}
        </div>
        
        {/* Name label */}
        <div className="mt-6 text-center">
          <div className="text-xl md:text-2xl font-semibold text-white drop-shadow-lg">
            {name}
          </div>
          {isBot && (
            <div className="text-sm text-green-100 mt-1 font-medium">AI Wellness Coach</div>
          )}
        </div>
      </div>

      {/* Speaking indicator with glow */}
      {isActive && (
        <>
          <div className={`absolute top-4 right-4 w-4 h-4 rounded-full animate-pulse ring-4 ${
            isBot ? "bg-green-400 ring-green-400/50" : "bg-blue-400 ring-blue-400/50"
          }`} />
          {/* Light focus glow effect when speaking */}
          <div className={`absolute inset-0 rounded-lg ${
            isBot 
              ? "bg-gradient-to-br from-green-400/20 via-emerald-400/15 to-teal-400/20 shadow-[0_0_40px_rgba(34,197,94,0.4)]" 
              : "bg-gradient-to-br from-blue-400/20 via-indigo-400/15 to-purple-400/20 shadow-[0_0_40px_rgba(59,130,246,0.4)]"
          } pointer-events-none animate-pulse`} />
        </>
      )}
    </div>
  );
}

/**
 * Stage component - Zoom-style side-by-side layout for two participants with logo-style avatars.
 */
function Stage() {
  // Get all audio tracks (not just microphone) to catch bot audio
  const allTrackRefs = useTracks([Track.Source.Microphone, Track.Source.Unknown]);
  const participants = useParticipants();

  // Get bot and user participants directly from participants array
  const botParticipant = participants.find((p) => p.identity === BOT_NAME);
  const userParticipant = participants.find((p) => p.identity !== BOT_NAME);

  // Get track refs for additional info
  const botRef = allTrackRefs.find((ref) => ref.participant.identity === BOT_NAME);
  const userRef = allTrackRefs.find((ref) => ref.participant.identity !== BOT_NAME);

  const botName = botParticipant?.name || BOT_NAME;
  const userName = userParticipant?.name || userRef?.participant.identity || "You";
  
  // State to track speaking - monitor both participant.isSpeaking and track state
  const [botSpeaking, setBotSpeaking] = React.useState(false);
  const [userSpeaking, setUserSpeaking] = React.useState(false);

  // Monitor speaking state for bot participant - use multiple detection methods
  React.useEffect(() => {
    if (!botParticipant) {
      setBotSpeaking(false);
      return;
    }

    let interval;
    let mounted = true;

    // Function to check if bot is speaking - use multiple methods for reliability
    const checkBotSpeaking = () => {
      if (!mounted || !botParticipant) return;

      // Method 1: Check participant.isSpeaking (primary method)
      let isSpeaking = botParticipant.isSpeaking ?? false;
      
      // Method 2: Check if bot has any active audio tracks
      let hasActiveAudio = false;
      
      // Check all audio tracks from the participant
      if (botParticipant.audioTracks && botParticipant.audioTracks.size > 0) {
        for (const [_, publication] of botParticipant.audioTracks) {
          if (publication && publication.track) {
            const track = publication.track;
            // If track is subscribed and not muted, consider it active
            if (track.isSubscribed && !track.isMuted) {
              hasActiveAudio = true;
              break;
            }
          }
        }
      }
      
      // Method 3: Check track refs (alternative source)
      if (botRef?.publication?.track) {
        const track = botRef.publication.track;
        if (track.isSubscribed && !track.isMuted) {
          hasActiveAudio = true;
        }
      }

      // Bot is speaking if participant.isSpeaking is true OR has active audio tracks
      // Prioritize isSpeaking, but also check audio tracks as fallback
      const speaking = isSpeaking || hasActiveAudio;
      
      if (mounted) {
        setBotSpeaking(speaking);
      }
    };

    // Check immediately
    checkBotSpeaking();
    
    // Poll speaking state every 50ms for very responsive updates
    interval = setInterval(checkBotSpeaking, 50);
    
    // Also listen to participant events
    const handleSpeakingChange = () => {
      if (mounted) checkBotSpeaking();
    };
    
    // Listen to track subscription events
    const trackUpdateHandler = () => {
      if (mounted) checkBotSpeaking();
    };
    
    // Subscribe to participant events if available
    try {
      if (botParticipant.on) {
        botParticipant.on("isSpeakingChanged", handleSpeakingChange);
      }
    } catch (e) {
      console.warn("Could not subscribe to bot participant events:", e);
    }
    
    // Subscribe to track events
    if (botParticipant.audioTracks) {
      for (const [_, publication] of botParticipant.audioTracks) {
        if (publication && publication.track) {
          const track = publication.track;
          try {
            if (track.on) {
              track.on("subscribed", trackUpdateHandler);
              track.on("unsubscribed", trackUpdateHandler);
              track.on("muted", trackUpdateHandler);
              track.on("unmuted", trackUpdateHandler);
            }
          } catch (e) {
            // Ignore errors
          }
        }
      }
    }
    
    return () => {
      mounted = false;
      clearInterval(interval);
      try {
        if (botParticipant && botParticipant.off) {
          botParticipant.off("isSpeakingChanged", handleSpeakingChange);
        }
      } catch (e) {
        // Ignore cleanup errors
      }
      if (botParticipant && botParticipant.audioTracks) {
        for (const [_, publication] of botParticipant.audioTracks) {
          if (publication && publication.track) {
            const track = publication.track;
            try {
              if (track.off) {
                track.off("subscribed", trackUpdateHandler);
                track.off("unsubscribed", trackUpdateHandler);
                track.off("muted", trackUpdateHandler);
                track.off("unmuted", trackUpdateHandler);
              }
            } catch (e) {
              // Ignore cleanup errors
            }
          }
        }
      }
    };
  }, [botParticipant, botRef]);

  // Monitor speaking state for user participant
  React.useEffect(() => {
    if (!userParticipant) {
      setUserSpeaking(false);
      return;
    }

    // Check initial state
    setUserSpeaking(userParticipant.isSpeaking ?? false);
    
    // Poll speaking state
    const interval = setInterval(() => {
      if (userParticipant) {
        setUserSpeaking(userParticipant.isSpeaking ?? false);
      }
    }, 100); // Check every 100ms for responsive updates
    
    return () => clearInterval(interval);
  }, [userParticipant]);

  return (
    <div className="flex-1 flex items-center justify-center p-4 md:p-8">
      <div className="w-full max-w-7xl h-full flex flex-col md:flex-row gap-4 md:gap-6">
        {/* User Participant - Left/Top */}
        <div
          className={`flex-1 relative rounded-lg overflow-hidden shadow-2xl transition-all duration-300 ${
            userSpeaking 
              ? "ring-4 ring-blue-400/60 shadow-[0_0_30px_rgba(59,130,246,0.5)] scale-[1.02]" 
              : "ring-2 ring-gray-700"
          }`}
          style={{ minHeight: "400px" }}
        >
          {userSpeaking && (
            <div className="absolute inset-0 bg-blue-400/10 animate-pulse pointer-events-none z-0" />
          )}
          <div className="relative z-10 w-full h-full">
            <ParticipantAvatar
              name={userName}
              isBot={false}
              isActive={userSpeaking}
            />
          </div>
        </div>

        {/* Bot Participant - Right/Bottom */}
        <div
          className={`flex-1 relative rounded-lg overflow-hidden shadow-2xl transition-all duration-300 ${
            botSpeaking 
              ? "ring-4 ring-green-400/60 shadow-[0_0_30px_rgba(34,197,94,0.5)] scale-[1.02]" 
              : "ring-2 ring-gray-700"
          }`}
          style={{ minHeight: "400px" }}
        >
          {botSpeaking && (
            <div className="absolute inset-0 bg-green-400/10 animate-pulse pointer-events-none z-0" />
          )}
          <div className="relative z-10 w-full h-full">
            <ParticipantAvatar
              name={botName}
              isBot={true}
              isActive={botSpeaking}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Room view component with Zoom-style interface.
 * @param {Object} props - Component props
 * @param {Object} props.roomData - Room connection data
 * @param {Function} props.onDisconnect - Callback when disconnecting
 */
export function RoomView({ roomData, onDisconnect }) {
  if (!roomData) {
    return null;
  }

  return (
    <LiveKitRoom
      video={false}
      audio={true}
      token={roomData.token}
      serverUrl={roomData.url}
      connect={true}
      className="h-screen w-screen flex flex-col bg-[#1a1a1a]"
    >
      {/* Zoom-style header */}
      <div className="bg-[#1a1a1a] border-b border-gray-800 px-4 md:px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 md:gap-3">
          <div className="w-8 h-8 md:w-10 md:h-10 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 flex items-center justify-center">
            <span className="text-xl md:text-2xl">🌿</span>
          </div>
          <div>
            <h2 className="text-base md:text-lg font-semibold text-white">Wellness Session</h2>
            <p className="text-xs text-gray-400 hidden md:block">Powered by {BOT_NAME}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs md:text-sm font-medium text-white">
            {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>
      </div>

      {/* Main content area - Zoom-style dark background */}
      <div className="flex-1 overflow-hidden bg-[#1a1a1a]">
        <Stage />
      </div>

      {/* Custom Zoom-style Audio Control Bar */}
      <ZoomControlBar onDisconnect={onDisconnect} />

      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

