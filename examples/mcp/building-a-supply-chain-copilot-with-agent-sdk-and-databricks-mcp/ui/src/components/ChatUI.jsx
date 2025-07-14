import React, { useState, useRef, useEffect } from "react";
import "./ChatUI.css";

export default function ChatUI() {
  const [messages, setMessages] = useState([
    { sender: "assistant", text: "Hi! How can I help you with your supply chain today?" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    const userMsg = { sender: "user", text: input };
    setMessages((msgs) => [...msgs, userMsg]);
    setLoading(true);
    setInput("");
    let assistantMsg = { sender: "assistant", text: "" };
    setMessages((msgs) => [...msgs, assistantMsg]);
    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input }),
      });
      if (!response.body) throw new Error("No response body");
      const reader = response.body.getReader();
      let done, value;
      while (!done) {
        ({ done, value } = await reader.read());
        if (value) {
          const text = new TextDecoder().decode(value);
          assistantMsg.text += text;
          setMessages((msgs) => {
            const copy = [...msgs];
            copy[copy.length - 1] = { ...assistantMsg };
            return copy;
          });
        }
      }
    } catch (err) {
      assistantMsg.text = "Sorry, there was an error connecting to the agent.";
      setMessages((msgs) => {
        const copy = [...msgs];
        copy[copy.length - 1] = { ...assistantMsg };
        return copy;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dbx-chat-root">
      <header className="dbx-chat-header">
        <span className="dbx-logo">🟥</span>
        <span className="dbx-title">Databricks Supply Chain Assistant</span>
      </header>
      <div className="dbx-chat-messages">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`dbx-chat-msg dbx-chat-msg--${msg.sender}`}
          >
            <div className="dbx-chat-bubble">{msg.text}</div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <form className="dbx-chat-input-bar" onSubmit={sendMessage}>
        <input
          type="text"
          className="dbx-chat-input"
          placeholder="Type your question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button
          className="dbx-chat-send-btn"
          type="submit"
          disabled={loading || !input.trim()}
        >
          {loading ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
