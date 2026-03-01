import { useState, useRef, useEffect } from "react";
import { Send, User, Loader2, AlertCircle, Trash2, Sparkles, Volume2, Mic, Square } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function ChatInterface() {
  // --- UPDATED BUDDY GREETING ---
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hello! I am Stellar, your AI Interviewer Buddy. Let's start with your background and what role you are looking for. Shall we begin?" }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  const [sessionId] = useState(() => {
    const stored = localStorage.getItem("chat_session_id");
    if (stored) return stored;
    const newId = `web-${Math.random().toString(36).substring(7)}`;
    localStorage.setItem("chat_session_id", newId);
    return newId;
  });

  // --- CONTINUOUS VOICE LOGIC (SR. TPM SPEC) ---
  const toggleListening = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return alert("Please use Chrome/Safari for voice features.");

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    } else {
      const recognition = new SpeechRecognition();
      recognition.lang = "en-US";
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onstart = () => setIsListening(true);

      recognition.onresult = (event: any) => {
        let finalTranscript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript;
          }
        }
        if (finalTranscript) setInput((prev) => prev + (prev ? " " : "") + finalTranscript);
      };

      recognition.onerror = (err: any) => {
        console.error("Speech Error:", err);
        setIsListening(false);
      };

      recognition.onend = () => setIsListening(false);

      recognitionRef.current = recognition;
      recognition.start();
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const clearSession = () => {
    localStorage.removeItem("chat_session_id");
    window.location.reload();
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;
    if (isListening) toggleListening();

    const userMsg = { role: "user" as const, content: input.trim() };
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
      if (data.reply) setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch (err) {
      setError("Connection failed. Is the backend running?");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 max-w-2xl mx-auto shadow-2xl border-x border-slate-200 font-sans">

      {/* Header */}
      <div className="bg-slate-900 p-4 text-white flex items-center justify-between shadow-md">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-emerald-400" />
          <h1 className="font-semibold text-lg tracking-wide text-emerald-50">Stellar <span className="text-slate-400 font-light">AI</span></h1>
        </div>
        <button onClick={clearSession} className="p-2 hover:bg-slate-700 rounded-full text-slate-400 hover:text-white transition-colors">
          <Trash2 size={18} />
        </button>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6 bg-slate-50">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex items-start gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`p-2 rounded-full shrink-0 shadow-sm ${msg.role === "user" ? "bg-slate-800 text-white" : "bg-emerald-100 text-emerald-700"}`}>
              {msg.role === "user" ? <User size={18} /> : <Sparkles size={18} />}
            </div>

            <div className="flex flex-col max-w-[85%] gap-1">
              <div className={`p-3.5 rounded-2xl text-sm shadow-sm leading-relaxed ${msg.role === "user"
                ? "bg-slate-800 text-white rounded-tr-none"
                : "bg-gray-200 text-gray-800 rounded-tl-none border border-gray-300"
                }`}>
                {msg.content}
              </div>

              {msg.role === "assistant" && (
                <button className="flex items-center gap-1.5 text-[10px] text-slate-400 hover:text-emerald-600 transition-colors font-bold ml-1 mt-1">
                  <Volume2 size={12} /> PLAY VOICE MESSAGE (DAY 6)
                </button>
              )}
            </div>
          </div>
        ))}
        {isLoading && <div className="text-slate-400 text-xs ml-12 flex gap-2 items-center italic"><Loader2 className="animate-spin w-3 h-3 text-emerald-500" /> Stella is thinking...</div>}
        {error && <div className="text-red-500 text-[10px] text-center p-2 bg-red-50 border border-red-100 rounded-lg mx-10 flex items-center justify-center gap-1"><AlertCircle size={12} /> {error}</div>}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-slate-200">
        <div className="flex gap-2 relative items-center">
          <button
            onClick={toggleListening}
            className={`p-4 rounded-full border transition-all duration-300 ${isListening
              ? "bg-red-500 border-red-600 text-white animate-pulse scale-110 shadow-lg"
              : "bg-slate-100 border-slate-200 text-slate-500 hover:bg-emerald-50 hover:text-emerald-600 hover:border-emerald-200"
              }`}
            title={isListening ? "Stop Recording" : "Start Recording"}
          >
            {isListening ? <Square size={20} fill="currentColor" /> : <Mic size={20} />}
          </button>

          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={isListening ? "I'm listening... talk to your buddy." : "Type your answer or tap the mic..."}
            className="flex-1 p-3 bg-slate-100 border-transparent rounded-xl focus:bg-white focus:border-emerald-500 focus:ring-4 focus:ring-emerald-50 outline-none transition-all placeholder:text-slate-400 text-sm resize-none h-12"
            disabled={isLoading}
          />

          <button
            onClick={sendMessage}
            disabled={isLoading || !input.trim()}
            className="bg-slate-900 text-white p-3.5 rounded-xl hover:bg-slate-800 disabled:opacity-30 transition-all shadow-md active:scale-95"
          >
            <Send size={18} />
          </button>
        </div>
        {isListening && <div className="text-center text-[10px] text-red-500 font-bold mt-2 animate-bounce uppercase">Live Recording • Tap Square to stop</div>}
      </div>
    </div>
  );
}