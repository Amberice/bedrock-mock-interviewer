import { useState, useRef, useEffect } from "react";
import { Send, User, Loader2, Trash2, Sparkles, Play, Pause, Star, Mic, Square } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
  audio?: string;
  score?: number;
  feedback?: string;
}

export default function ChatInterface() {
  // ✅ Option A: env-driven with safe fallback (prevents "undefined")
  const API_BASE =
    (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ||
    "https://kufcqcoy2d.execute-api.us-east-1.amazonaws.com/prod";

  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hello! I'm Stellar, your AI Interviewer. Let's start with your background and what role you are looking for. By the end of this session, I will rate your answers and provide a scorecard. Shall we begin?",
    },
  ]);

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState<number | null>(null);
  const [isListening, setIsListening] = useState(false);

  // --- REFS ---
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // NEW: Refs for robust speech stability
  const isUserStopped = useRef(false);
  const interimRef = useRef("");

  const [sessionId] = useState(() => localStorage.getItem("chat_session_id") || `web-${Math.random()}`);

  // --- AUTO-RESIZE LOGIC ---
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  // --- AUDIO PLAYBACK ---
  const playAudio = (b64: string, idx: number) => {
    if (isPlaying === idx) {
      audioRef.current?.pause();
      setIsPlaying(null);
      return;
    }
    if (audioRef.current) audioRef.current.pause();

    const byteCharacters = atob(b64);
    const byteNumbers = new Array(byteCharacters.length).fill(0).map((_, i) => byteCharacters.charCodeAt(i));
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: "audio/mpeg" });

    const audio = new Audio(URL.createObjectURL(blob));
    audioRef.current = audio;
    setIsPlaying(idx);
    audio.play();
    audio.onended = () => setIsPlaying(null);
  };

  // --- ROBUST SPEECH RECOGNITION ---
  const toggleListening = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return alert("Use Chrome for voice features.");

    if (isListening) {
      isUserStopped.current = true;
      recognitionRef.current?.stop();
      setIsListening(false);
    } else {
      isUserStopped.current = false;
      interimRef.current = "";

      const recognition = new SpeechRecognition();
      recognition.lang = "en-US";
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onstart = () => setIsListening(true);

      recognition.onresult = (event: any) => {
        let finalChunk = "";
        let interimChunk = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalChunk += event.results[i][0].transcript;
          } else {
            interimChunk += event.results[i][0].transcript;
          }
        }

        if (finalChunk) {
          setInput((prev) => (prev + " " + finalChunk).trim());
          interimRef.current = "";
        } else {
          interimRef.current = interimChunk;
        }
      };

      recognition.onerror = (err: any) => {
        console.warn("Mic Error:", err);
        if (err.error === "no-speech") return;
      };

      recognition.onend = () => {
        if (!isUserStopped.current) {
          if (interimRef.current) {
            const lostText = interimRef.current;
            setInput((prev) => (prev + " " + lostText).trim());
            interimRef.current = "";
          }
          console.log("Browser stopped mic. Restarting...");
          recognition.start();
        } else {
          setIsListening(false);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    }
  };

  // --- SEND MESSAGE ---
  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    if (isListening) {
      isUserStopped.current = true;
      recognitionRef.current?.stop();
      setIsListening(false);
    }

    const userMsg = { role: "user" as const, content: input };
    setMessages((p) => [...p, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const url = `${API_BASE}/chat`; // ✅ always valid, never "undefined"
      console.log("Calling API:", url);

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: userMsg.content }),
      });

      // If you accidentally hit an HTML page (Amplify 404), res.json() will throw.
      const contentType = res.headers.get("content-type") || "";
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status} ${res.statusText}. Body: ${errText.slice(0, 300)}`);
      }

      if (!contentType.includes("application/json")) {
        const text = await res.text();
        throw new Error(`Expected JSON but got "${contentType}". Body: ${text.slice(0, 300)}`);
      }

      const data = await res.json();

      setMessages((p) => [
        ...p,
        {
          role: "assistant",
          content: data.reply,
          audio: data.audio,
          score: data.score,
          feedback: data.feedback,
        },
      ]);
    } catch (e) {
      console.error("SendMessage error:", e);
      setMessages((p) => [
        ...p,
        {
          role: "assistant",
          content: `⚠️ Error calling API. Check console logs for details.`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-100 font-sans max-w-lg mx-auto border-x border-slate-800">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 bg-slate-900/90 backdrop-blur flex justify-between items-center sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <Sparkles className="text-emerald-400 w-5 h-5" />
          <h1 className="font-bold text-lg">
            Stellar<span className="text-slate-500 font-light">AI</span>
          </h1>
        </div>
        <button onClick={() => window.location.reload()}>
          <Trash2 size={18} className="text-slate-500 hover:text-white" />
        </button>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${m.role === "user" ? "bg-indigo-600" : "bg-emerald-600"
                }`}
            >
              {m.role === "user" ? <User size={16} /> : <Sparkles size={16} />}
            </div>

            <div className="flex flex-col gap-2 max-w-[85%]">
              <div
                className={`p-3 rounded-2xl text-sm leading-relaxed ${m.role === "user" ? "bg-indigo-600" : "bg-slate-800 border border-slate-700"
                  }`}
              >
                {m.content}
              </div>

              {m.score && m.score > 0 && (
                <div className="flex gap-2 text-xs bg-slate-800/50 p-2 rounded-lg border border-slate-700/50 items-center">
                  <div className="flex items-center gap-1 text-yellow-400 font-bold">
                    <Star size={12} fill="currentColor" /> {m.score}/10
                  </div>
                  <span className="text-slate-400 border-l border-slate-700 pl-2 italic">{m.feedback}</span>
                </div>
              )}

              {m.audio && (
                <button
                  onClick={() => playAudio(m.audio!, i)}
                  className="flex items-center gap-2 text-xs font-bold text-slate-400 hover:text-emerald-400 transition-colors w-fit"
                >
                  {isPlaying === i ? <Pause size={12} /> : <Play size={12} />}
                  {isPlaying === i ? "PLAYING..." : "PLAY VOICE"}
                </button>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="ml-12 text-slate-500 text-xs flex gap-2 items-center">
            <Loader2 className="animate-spin w-3 h-3" /> Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-slate-900 border-t border-slate-800 flex gap-2 items-end">
        <button
          onClick={toggleListening}
          className={`p-3 rounded-full mb-1 transition-all ${isListening ? "bg-red-500 animate-pulse text-white" : "bg-slate-800 text-slate-400 hover:text-white"
            }`}
        >
          {isListening ? <Square size={20} fill="currentColor" /> : <Mic size={20} />}
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          className="flex-1 bg-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none overflow-y-auto max-h-[33vh]"
          placeholder="Type or speak..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
        />

        <button
          onClick={sendMessage}
          className="bg-emerald-600 p-3 rounded-xl hover:bg-emerald-500 mb-1 transition-colors text-white"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}