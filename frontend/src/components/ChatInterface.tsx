import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2, AlertCircle, Trash2, Sparkles, Volume2, Mic, MicOff, Square } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hello! I am your AI Interviewer. Ready to start?" }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // --- 1. SESSION PERSISTENCE ---
  const [sessionId] = useState(() => {
    const stored = localStorage.getItem("chat_session_id");
    if (stored) return stored;
    const newId = `web-${Math.random().toString(36).substring(7)}`;
    localStorage.setItem("chat_session_id", newId);
    return newId;
  });

  // --- 2. HUMAN-LIKE VOICE LOGIC ---
  const speak = (text: string) => {
    window.speechSynthesis.cancel();

    // Clean Markdown symbols (#, *, etc.) so it doesn't say "hash hash"
    const cleanText = text.replace(/[#*`_~]/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);

    const voices = window.speechSynthesis.getVoices();

    // Priority list of "human" sounding voices
    const preferredVoices = [
      "Google US English",
      "Microsoft Aria Online",
      "Microsoft Jenny Online",
      "English (United States)",
      "Apple Samantha"
    ];

    let selectedVoice = null;
    for (const name of preferredVoices) {
      selectedVoice = voices.find(v => v.name.includes(name));
      if (selectedVoice) break;
    }

    if (!selectedVoice) {
      selectedVoice = voices.find(v => v.name.includes("Natural") || v.name.includes("Google"));
    }

    if (selectedVoice) utterance.voice = selectedVoice;

    utterance.rate = 0.9; // Human-like pacing
    utterance.pitch = 1.0;

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);

    window.speechSynthesis.speak(utterance);
  };

  const stopSpeaking = () => {
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  };

  // --- 3. MICROPHONE LOGIC (Voice to Text) ---
  const toggleListening = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return alert("Please use Chrome for voice features.");

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";

    if (!isListening) {
      recognition.start();
      setIsListening(true);
    } else {
      recognition.stop();
      setIsListening(false);
    }

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setInput(transcript);
      setIsListening(false);
    };

    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);
  };

  // --- 4. CHAT LOGIC ---
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    // Pre-load voices for the browser
    window.speechSynthesis.getVoices();
  }, [messages]);

  const clearSession = () => {
    localStorage.removeItem("chat_session_id");
    window.speechSynthesis.cancel();
    window.location.reload();
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;
    const userMsg = { role: "user" as const, content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: userMsg.content }),
      });
      const data = await response.json();
      if (data.reply) {
        setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      }
    } catch (err) {
      setError("Connection failed.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 max-w-2xl mx-auto shadow-2xl border-x border-slate-200 font-sans">
      {/* Header */}
      <div className="bg-blue-600 p-4 text-white flex items-center justify-between shadow-md">
        <div className="flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-yellow-300" />
          <h1 className="font-bold text-lg tracking-wide">Stellar Interviewer</h1>
        </div>
        <div className="flex items-center gap-3">
          {isSpeaking && (
            <button onClick={stopSpeaking} className="flex items-center gap-1 bg-red-500 px-2 py-1 rounded text-[10px] animate-pulse">
              <Square size={10} fill="currentColor" /> Stop Voice
            </button>
          )}
          <span className="text-xs opacity-75 hidden sm:inline">Session: {sessionId.slice(-6)}</span>
          <button onClick={clearSession} title="New Chat" className="p-1 hover:bg-blue-500 rounded">
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex items-start gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`p-2 rounded-full shrink-0 ${msg.role === "user" ? "bg-blue-500 text-white" : "bg-emerald-600 text-white"}`}>
              {msg.role === "user" ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className="flex flex-col max-w-[85%] gap-1">
              <div className={`p-3.5 rounded-2xl text-sm shadow-sm leading-relaxed ${msg.role === "user" ? "bg-blue-600 text-white rounded-tr-none" : "bg-white text-gray-800 rounded-tl-none border border-slate-200"}`}>
                {msg.content}
              </div>
              {msg.role === "assistant" && (
                <div className="flex gap-3 ml-1">
                  <button onClick={() => speak(msg.content)} className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-blue-600 transition-colors">
                    <Volume2 size={12} /> Listen
                  </button>
                  {isSpeaking && (
                    <button onClick={stopSpeaking} className="flex items-center gap-1 text-[10px] text-red-400 hover:text-red-600">
                      <Square size={10} fill="currentColor" /> Stop
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && <div className="text-slate-400 text-sm ml-12 flex gap-2"><Loader2 className="animate-spin w-4 h-4" /> Thinking...</div>}
        {error && <div className="text-red-500 text-sm text-center p-2"><AlertCircle size={16} className="inline mr-1" />{error}</div>}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-slate-200">
        <div className="flex gap-2 relative">
          <button
            onClick={toggleListening}
            className={`p-3 rounded-xl border transition-all ${isListening ? "bg-red-100 border-red-300 text-red-600 animate-pulse" : "bg-slate-100 border-slate-200 text-slate-500 hover:bg-slate-200"}`}
            title="Speak your answer"
          >
            {isListening ? <MicOff size={20} /> : <Mic size={20} />}
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder={isListening ? "Listening..." : "Type or speak your answer..."}
            className="flex-1 p-3 bg-slate-100 border-transparent rounded-xl focus:bg-white focus:border-blue-500 outline-none transition-all"
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !input.trim()}
            className="bg-blue-600 text-white p-3 rounded-xl hover:bg-blue-700 disabled:opacity-50 shadow-sm"
          >
            <Send size={20} />
          </button>
        </div>
        <div className="text-center text-xs text-slate-400 mt-2">Powered by Amazon Bedrock • Nova Micro</div>
      </div>
    </div>
  );
}