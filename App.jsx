import { useState } from "react";
import axios from "axios";

function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);

  const askQuestion = async () => {
    if (!question.trim()) return;
    setAnswer("Loading...");
    try {
      const res = await axios.get("http://localhost:8000/qa", {
        params: { q: question }
      });
      setAnswer(res.data.answer);
      setSources(res.data.sources || []);
    } catch (err) {
      setAnswer("Error: " + err.message);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center p-8 bg-gray-100">
      <h1 className="text-2xl font-bold mb-4">Confluence Q&A</h1>
      <div className="w-full max-w-xl bg-white p-4 rounded shadow">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question..."
          className="w-full border p-2 rounded mb-2"
        />
        <button
          onClick={askQuestion}
          className="bg-blue-600 text-white px-4 py-2 rounded"
        >
          Ask
        </button>
        <div className="mt-4">
          <h2 className="font-semibold">Answer:</h2>
          <p className="whitespace-pre-line">{answer}</p>
        </div>
        {sources.length > 0 && (
          <div className="mt-4">
            <h3 className="font-semibold">Sources:</h3>
            <ul className="list-disc pl-5">
              {sources.map((s, i) => (
                <li key={i}>
                  <a href={s} target="_blank" rel="noopener noreferrer" className="text-blue-500">
                    {s}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
