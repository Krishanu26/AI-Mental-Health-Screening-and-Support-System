import React from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = "";

function App() {
  const [questions, setQuestions] = React.useState([]);
  const [answers, setAnswers] = React.useState({});
  const [storageConsent, setStorageConsent] = React.useState(false);
  const [researchConsent, setResearchConsent] = React.useState(false);
  const [result, setResult] = React.useState(null);
  const [feedbackBusy, setFeedbackBusy] = React.useState(false);
  const [feedbackSaved, setFeedbackSaved] = React.useState(null);
  const [feedbackError, setFeedbackError] = React.useState("");
  const [health, setHealth] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [chatText, setChatText] = React.useState("");
  const [chatReply, setChatReply] = React.useState("");
  const [chatBusy, setChatBusy] = React.useState(false);

  React.useEffect(() => {
    fetch(`${API}/api/questions`)
      .then(async r => {
        if (!r.ok) throw new Error("Could not load assessment questions.");
        return r.json();
      })
      .then(d => setQuestions(Array.isArray(d.questions) ? d.questions : []))
      .catch(err => setError(err.message || "Cannot reach Flask API. Start main.py."));
    fetch(`${API}/api/health`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setHealth)
      .catch(() => setHealth({mongodb:"unavailable"}));
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (questions.length !== 21 || Object.keys(answers).length !== questions.length) {
      setError("Please answer all 21 questions before submitting.");
      return;
    }
    if (researchConsent && !storageConsent) {
      setError("Research participation requires separate assessment-storage consent.");
      return;
    }
    setBusy(true);
    setResult(null);
    setFeedbackSaved(null);
    setFeedbackError("");
    try {
      const responses = questions.map((_, i) => Number(answers[i]));
      const res = await fetch(`${API}/api/assessment`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({responses, storage_consent:storageConsent, research_consent:researchConsent})
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Assessment submission failed.");
      setResult(data);
    } catch (err) {
      setError(err.message || "Assessment submission failed.");
    } finally {
      setBusy(false);
    }
  }

  async function sendChat(e) {
    e.preventDefault();
    const message = chatText.trim();
    if (!message || chatBusy) return;
    setChatBusy(true);
    setChatReply("");
    try {
      const res = await fetch(`${API}/api/chat`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({message})
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Chat service is unavailable.");
      setChatReply(data.reply || "No response was returned.");
      setChatText("");
    } catch (err) {
      setChatReply(err.message || "Chat service is unavailable.");
    } finally {
      setChatBusy(false);
    }
  }

  async function submitRecommendationFeedback(followed) {
    if (!result?.feedback_token || feedbackBusy) return;
    setFeedbackBusy(true);
    setFeedbackError("");
    try {
      const res = await fetch(
        `${API}/api/assessment/feedback/${encodeURIComponent(result.feedback_token)}/recommendation-feedback`,
        {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({followed})}
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not save your response.");
      setFeedbackSaved(followed);
    } catch (err) {
      setFeedbackError(err.message);
    } finally {
      setFeedbackBusy(false);
    }
  }

  return <main className="shell">
    <header>
      <div className="mark">ORI</div>
      <div><h1>Wellbeing Companion</h1><p>Private local-development assessment interface</p></div>
      <span className={`status ${health?.mongodb==="connected"?"ok":"warn"}`}>{health?.mongodb || "Checking database…"}</span>
    </header>
    <section className="notice"><strong>Important:</strong> This questionnaire is a screening aid, not a diagnosis or treatment. It is not a substitute for a qualified mental-health professional.</section>
    {error && <section className="notice" role="alert">{error}</section>}
    {health?.mongodb !== "connected" && <p className="muted">Database is unavailable. You can still complete an assessment without saving it.</p>}
    <form onSubmit={submit} className="panel">
      <h2>Assessment</h2><p className="muted">Select one response for each question.</p>
      {questions.map((q, i) => <fieldset key={i}>
        <legend>{q.question}</legend>
        {q.options.map((o, j) => <label className="option" key={j}>
          <input type="radio" name={`q${i}`} value={j} checked={String(answers[i])===String(j)}
            onChange={() => setAnswers(a=>({...a,[i]:j}))}/>
          <span>{o.text}</span>
        </label>)}
      </fieldset>)}
      <div className="consents">
        <label><input type="checkbox" checked={storageConsent} onChange={e=>setStorageConsent(e.target.checked)}/> I consent to saving my assessment responses and score in the configured database. Optional.</label>
        <label><input type="checkbox" checked={researchConsent} onChange={e=>setResearchConsent(e.target.checked)}/> Separately, I consent to use of de-identified responses for experimental research/model training. Optional and requires storage consent.</label>
      </div>
      <button disabled={busy || questions.length!==21}>{busy?"Processing…":"Submit assessment"}</button>
    </form>
    {result && <section className="panel result">
      <h2>Your screening result</h2><div className="score">{result.total_score} / 63</div>
      <h3>{result.risk_level}</h3><p>{result.notice}</p>
      {result.safety_guidance && <p className="notice" role="alert">{result.safety_guidance}</p>}
      <p className="muted">{result.storage_notice}</p>
      <h3>Suggested next steps</h3>
      <ul>{(result.recommendations?.main_recommendations || []).map((x,i)=><li key={i}>{x}</li>)}</ul>
      {result.saved && <div className="feedback">
        <h3>Did you follow any of these suggestions?</h3>
        <p className="muted">Optional. Your answer is saved with this assessment. This app does not track physical movement.</p>
        <button type="button" disabled={feedbackBusy || feedbackSaved!==null} onClick={()=>submitRecommendationFeedback(true)}>Yes</button>
        <button type="button" disabled={feedbackBusy || feedbackSaved!==null} onClick={()=>submitRecommendationFeedback(false)}>No</button>
        {feedbackSaved !== null && <p role="status">Your response was saved.</p>}
        {feedbackError && <p role="alert">{feedbackError}</p>}
      </div>}
      {result.assessment_id && <p className="muted">Feedback token: {result.feedback_token ? "available" : "not issued"}</p>}
    </section>}
    <section className="panel">
      <h2>Supportive chat</h2><p className="muted">Optional local Ollama integration. It does not diagnose or provide crisis support.</p>
      <form onSubmit={sendChat} className="chatrow">
        <input value={chatText} onChange={e=>setChatText(e.target.value)} maxLength={4000} placeholder="Write a message…" />
        <button type="submit" disabled={chatBusy || !chatText.trim()}>{chatBusy?"Sending…":"Send"}</button>
      </form>
      {chatReply && <p className="chatreply" role="status">{chatReply}</p>}
    </section>
    <footer>ORI AI · Local development prototype · Experimental ML is not used to determine your screening category.</footer>
  </main>;
}
createRoot(document.getElementById("root")).render(<App />);
