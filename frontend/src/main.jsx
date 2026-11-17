import React from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = "http://127.0.0.1:5000";

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
  const [chatText, setChatText] = React.useState("");
  const [chatReply, setChatReply] = React.useState("");

  React.useEffect(() => {
    fetch(`${API}/api/questions`).then(r => r.json()).then(d => setQuestions(d.questions || []))
      .catch(() => setHealth({error:"Cannot reach Flask API. Check that main.py is running."}));
    fetch(`${API}/api/health`).then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    if (Object.keys(answers).length !== questions.length) {
      alert("Please answer every question before submitting."); return;
    }
    if (!storageConsent) {
      alert("Please provide storage consent, or do not submit/store this assessment."); return;
    }
    setBusy(true); setResult(null);
    setFeedbackSaved(null); setFeedbackError("");
    try {
      const responses = questions.map((_, i) => Number(answers[i]));
      const res = await fetch(`${API}/api/assessment`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({responses, storage_consent:storageConsent, research_consent:researchConsent})
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Submission failed");
      setResult(data);
    } catch (err) { alert(err.message); }
    finally { setBusy(false); }
  }

  async function sendChat(e) {
    e.preventDefault(); if (!chatText.trim()) return;
    try {
      const res = await fetch(`${API}/api/chat`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:chatText})});
      const data = await res.json(); setChatReply(data.reply || data.error || "No response");
    } catch { setChatReply("Chat service is unavailable."); }
  }

  async function submitRecommendationFeedback(followed) {
    setFeedbackBusy(true);
    setFeedbackError("");
    try {
      const res = await fetch(
        `${API}/api/assessment/${encodeURIComponent(result.assessment_id)}/recommendation-feedback`,
        {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({followed})
        }
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
    <header><div className="mark">ORI</div><div><h1>Wellbeing Companion</h1><p>Private local-development assessment interface</p></div>
      <span className={`status ${health?.mongodb==="connected"?"ok":"warn"}`}>{health?.mongodb || "Checking database…"}</span>
    </header>
    <section className="notice"><strong>Important:</strong> This questionnaire is a screening aid, not a diagnosis or treatment. It is not a substitute for a qualified mental-health professional.</section>
    {health?.error && <section className="notice">{health.error}</section>}
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
        <label><input type="checkbox" checked={storageConsent} onChange={e=>setStorageConsent(e.target.checked)}/> I consent to saving my assessment responses and score in the configured database.</label>
        <label><input type="checkbox" checked={researchConsent} onChange={e=>setResearchConsent(e.target.checked)}/> Separately, I consent to use of de-identified responses for experimental research/model training. This is optional.</label>
      </div>
      <button disabled={busy || questions.length===0}>{busy?"Saving…":"Submit assessment"}</button>
    </form>
    {result && <section className="panel result">
      <h2>Your screening result</h2><div className="score">{result.total_score} / 63</div>
      <h3>{result.risk_level}</h3><p>{result.notice}</p>
      {result.self_harm_item_positive && <p className="notice">Your response indicates that it may be important to speak promptly with a qualified professional or trusted person. If you are in immediate danger, contact local emergency services now.</p>}
      <h3>Suggested next steps</h3>
      <ul>{(result.recommendations?.main_recommendations || []).map((x,i)=><li key={i}>{x}</li>)}</ul>
      <div className="feedback">
        <h3>Did you follow any of these suggestions?</h3>
        <p className="muted">Optional. Your answer is saved with this assessment. This app does not track physical movement.</p>
        <button type="button" disabled={feedbackBusy} onClick={()=>submitRecommendationFeedback(true)}>Yes</button>
        <button type="button" disabled={feedbackBusy} onClick={()=>submitRecommendationFeedback(false)}>No</button>
        {feedbackSaved !== null && <p role="status">Your response was saved.</p>}
        {feedbackError && <p role="alert">{feedbackError}</p>}
      </div>
      <p className="muted">Assessment saved. Reference: {result.assessment_id}</p>
    </section>}
    <section className="panel">
      <h2>Supportive chat</h2><p className="muted">Optional local Ollama integration. It does not diagnose or provide crisis support.</p>
      <form onSubmit={sendChat} className="chatrow"><input value={chatText} onChange={e=>setChatText(e.target.value)} placeholder="Write a message…" /><button type="submit">Send</button></form>
      {chatReply && <p className="chatreply">{chatReply}</p>}
    </section>
    <footer>ORI AI · Local development prototype · Experimental ML is not used to determine your screening category.</footer>
  </main>;
}
createRoot(document.getElementById("root")).render(<App />);
