import React, { useState, useEffect } from 'https://esm.sh/react@18';
import ReactDOM from 'https://esm.sh/react-dom@18/client';

const API_BASE = 'http://localhost:8000';
const COMPANY_BASE = 'http://localhost:8001';
const EMAIL_BASE = 'http://localhost:8002';

function App() {
  const [activeTab, setActiveTab] = useState('tasks');
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [schedulerRuns, setSchedulerRuns] = useState([]);
  const [clockInfo, setClockInfo] = useState(null);
  const [clockOverrideInput, setClockOverrideInput] = useState('');
  
  // New task form state
  const [taskGoal, setTaskGoal] = useState('Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.');
  const [taskWorkflow, setTaskWorkflow] = useState('invoice_processing');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [humanAnswer, setHumanAnswer] = useState({});

  // Poll system state
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2500);
    return () => clearInterval(interval);
  }, [selectedTask?.id]);

  async function fetchData() {
    try {
      // 1. Clock
      const cRes = await fetch(`${API_BASE}/api/clock`);
      if (cRes.ok) setClockInfo(await cRes.json());

      // 2. Tasks
      const tRes = await fetch(`${API_BASE}/api/tasks`);
      if (tRes.ok) {
        const tData = await tRes.json();
        setTasks(tData);
        if (selectedTask) {
          const freshSelected = tData.find(t => t.id === selectedTask.id);
          if (freshSelected) {
            // Also fetch steps
            const sRes = await fetch(`${API_BASE}/api/tasks/${selectedTask.id}`);
            if (sRes.ok) setSelectedTask(await sRes.json());
          }
        }
      }

      // 3. Questions
      const qRes = await fetch(`${API_BASE}/api/questions`);
      if (qRes.ok) setQuestions(await qRes.json());

      // 4. Scheduler runs
      const rRes = await fetch(`${API_BASE}/api/scheduler/runs`);
      if (rRes.ok) setSchedulerRuns(await rRes.json());
    } catch (e) {
      console.error('Fetch error:', e);
    }
  }

  async function handleCreateTask(e) {
    e.preventDefault();
    if (!taskGoal.trim()) return;
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: taskGoal,
          workflow_id: taskWorkflow
        })
      });
      const data = await res.json();
      if (data.task_id) {
        await fetchData();
        // Auto-select newly created task
        const newTask = await (await fetch(`${API_BASE}/api/tasks/${data.task_id}`)).json();
        setSelectedTask(newTask);
        setActiveTab('task_detail');
      }
    } catch (err) {
      alert('Error creating task: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAnswerQuestion(qId, answer) {
    if (!answer) return;
    try {
      await fetch(`${API_BASE}/api/questions/${qId}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer })
      });
      fetchData();
    } catch (err) {
      alert('Error answering question: ' + err.message);
    }
  }

  async function handleTriggerScheduler() {
    try {
      const res = await fetch(`${API_BASE}/api/scheduler/run-now`, { method: 'POST' });
      const data = await res.json();
      alert(`Payment follow-up run completed!\nInvoices checked: ${data.invoices_checked}\nReminders dispatched: ${data.reminders_sent}`);
      fetchData();
    } catch (err) {
      alert('Scheduler error: ' + err.message);
    }
  }

  async function handleClearTasks() {
    if (!confirm('Are you sure you want to remove all task execution history?')) return;
    try {
      await fetch(`${API_BASE}/api/tasks`, { method: 'DELETE' });
      setSelectedTask(null);
      await fetchData();
    } catch (err) {
      alert('Error clearing tasks: ' + err.message);
    }
  }

  async function handleSetClockOverride() {
    try {
      await fetch(`${API_BASE}/api/clock/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override_datetime: clockOverrideInput || null })
      });
      fetchData();
    } catch (err) {
      alert('Clock override error: ' + err.message);
    }
  }

  return (
    <div>
      {/* Top Header */}
      <header>
        <div className="header-container">
          <div className="logo-group">
            <div className="logo-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            </div>
            <div className="logo-text">centrAlign <span>Autonomous Worker</span></div>
          </div>

          <div className="nav-tabs">
            <button className={`nav-tab ${activeTab === 'tasks' ? 'active' : ''}`} onClick={() => setActiveTab('tasks')}>🚀 Tasks & Launch</button>
            <button className={`nav-tab ${activeTab === 'task_detail' ? 'active' : ''}`} onClick={() => setActiveTab('task_detail')}>
              🔍 Inspector {selectedTask ? `(${selectedTask.id})` : ''}
            </button>
            <button className={`nav-tab ${activeTab === 'human_queue' ? 'active' : ''}`} onClick={() => setActiveTab('human_queue')}>
              🙋 Human Queue {questions.length > 0 && <span style={{color: '#f59e0b', fontWeight: 800}}>({questions.length})</span>}
            </button>
            <button className={`nav-tab ${activeTab === 'scheduler' ? 'active' : ''}`} onClick={() => setActiveTab('scheduler')}>⏰ Follow-up Scheduler</button>
            <button className={`nav-tab ${activeTab === 'apps' ? 'active' : ''}`} onClick={() => setActiveTab('apps')}>🏢 Apps & Controls</button>
          </div>

          {/* Dev Clock Widget */}
          <div className="dev-clock-widget">
            <div className="clock-display" title="System Injectable Clock">
              <span className={`status-dot ${clockInfo?.is_business_hours ? '' : 'inactive'}`}></span>
              <span>{clockInfo?.current_time ? clockInfo.current_time.substring(11, 19) : '--:--:--'}</span>
              <span style={{color: '#94a3b8', fontSize: '0.75rem'}}>{clockInfo?.is_business_hours ? 'BIZ HOURS' : 'AFTER HOURS'}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main>
        {activeTab === 'tasks' && (
          <div className="grid-2">
            {/* Task Launch Card */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">✨ Submit Autonomous Task</div>
                <span style={{fontSize: '0.8rem', color: '#94a3b8'}}>Single-Agent Runtime</span>
              </div>
              <form onSubmit={handleCreateTask}>
                <div style={{marginBottom: '1rem'}}>
                  <label style={{display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '0.4rem'}}>Workflow Configuration:</label>
                  <select value={taskWorkflow} onChange={e => setTaskWorkflow(e.target.value)}>
                    <option value="invoice_processing">Workflow A: Accounts Payable Invoice Processing</option>
                    <option value="scheduled_payment_followup">Workflow B: Scheduled Payment Follow-up</option>
                    <option value="vendor_summary_report">Workflow C (Generalization): Vendor Balance Audit Report</option>
                  </select>
                </div>

                <div style={{marginBottom: '1.25rem'}}>
                  <label style={{display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '0.4rem'}}>Natural Language Goal / Instruction:</label>
                  <textarea rows="4" value={taskGoal} onChange={e => setTaskGoal(e.target.value)} required placeholder="Type natural language instructions..."></textarea>
                </div>

                <div style={{display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', flexWrap: 'wrap'}}>
                  <span style={{fontSize: '0.8rem', color: '#94a3b8', width: '100%'}}>Quick Presets:</span>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
                    setTaskWorkflow('invoice_processing');
                    setTaskGoal('Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.');
                  }}>Target Challenge: Latest Company X Invoice</button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
                    setTaskWorkflow('invoice_processing');
                    setTaskGoal('Find the new invoice from Nova Tech, extract the amount and due date, enter it into our internal system, and tell me once it is done.');
                  }}>Brand New Bill: Nova Tech ($3,450)</button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
                    setTaskWorkflow('scheduled_payment_followup');
                    setTaskGoal('Audit overdue invoices, check business hour eligibility, and dispatch reminders with idempotency verification.');
                  }}>Payment Follow-up Audit</button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
                    setTaskWorkflow('vendor_summary_report');
                    setTaskGoal('Audit all invoices for vendor Company X, calculate total settled versus outstanding balances, and compile an audit summary.');
                  }}>Generalization: Vendor Summary</button>
                </div>

                <button type="submit" className="btn btn-primary" style={{width: '100%'}} disabled={isSubmitting}>
                  {isSubmitting ? 'Dispatching...' : '🚀 Launch Autonomous Task'}
                </button>
              </form>
            </div>

            {/* Real Task History List */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">📜 Execution Tasks ({tasks.length})</div>
                <div style={{display: 'flex', gap: '0.5rem'}}>
                  {tasks.length > 0 && (
                    <button className="btn btn-secondary btn-sm" style={{color: '#f87171', borderColor: '#ef444455'}} onClick={handleClearTasks}>🗑 Clear History</button>
                  )}
                  <button className="btn btn-secondary btn-sm" onClick={fetchData}>↻ Refresh</button>
                </div>
              </div>

              <div style={{maxHeight: '520px', overflowY: 'auto'}}>
                {tasks.map(t => (
                  <div key={t.id} className={`task-item ${selectedTask?.id === t.id ? 'selected' : ''}`} onClick={async () => {
                    const sRes = await fetch(`${API_BASE}/api/tasks/${t.id}`);
                    setSelectedTask(await sRes.json());
                    setActiveTab('task_detail');
                  }}>
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem'}}>
                      <span style={{fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8'}}>{t.id}</span>
                      <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                        <span className={`badge badge-${t.status}`}>{t.status}</span>
                        <button
                          style={{background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '0.9rem', padding: '0 4px', lineHeight: 1}}
                          title="Remove this task"
                          onClick={async (e) => {
                            e.stopPropagation();
                            await fetch(`${API_BASE}/api/tasks/${t.id}`, { method: 'DELETE' });
                            if (selectedTask?.id === t.id) setSelectedTask(null);
                            fetchData();
                          }}
                        >✕</button>
                      </div>
                    </div>
                    <div style={{fontSize: '0.9rem', color: '#f8fafc', fontWeight: 500, marginBottom: '0.5rem'}}>{t.goal}</div>
                    <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: '#94a3b8'}}>
                      <span>Steps: {t.step_count} | LLM Calls: {t.llm_call_count}</span>
                      <span>{t.created_at?.substring(11, 19)}</span>
                    </div>
                  </div>
                ))}
                {tasks.length === 0 && (
                  <div style={{textAlign: 'center', color: '#94a3b8', padding: '3rem'}}>No tasks executed yet. Submit a task above.</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'task_detail' && (
          <div>
            {!selectedTask ? (
              <div className="card" style={{textAlign: 'center', padding: '4rem', color: '#94a3b8'}}>
                <h3>No Task Selected</h3>
                <p style={{marginTop: '0.5rem'}}>Select a task from the Tasks tab to view its step-by-step action history and verification evidence.</p>
                <button className="btn btn-primary" style={{marginTop: '1.5rem'}} onClick={() => setActiveTab('tasks')}>Go to Tasks</button>
              </div>
            ) : (
              <div>
                <div className="card" style={{marginBottom: '1.5rem'}}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem'}}>
                    <div>
                      <div style={{display: 'flex', alignItems: 'center', gap: '0.75rem'}}>
                        <h2 style={{fontSize: '1.4rem', fontWeight: 800}}>{selectedTask.id}</h2>
                        <span className={`badge badge-${selectedTask.status}`}>{selectedTask.status}</span>
                      </div>
                      <p style={{fontSize: '1rem', color: '#cbd5e1', marginTop: '0.35rem'}}>{selectedTask.goal}</p>
                    </div>
                    <div style={{textAlign: 'right', fontSize: '0.85rem', color: '#94a3b8'}}>
                      <div>Workflow: <strong style={{color: '#fff'}}>{selectedTask.workflow_id}</strong></div>
                      <div>Total Steps: <strong style={{color: '#38bdf8'}}>{selectedTask.step_count}</strong> | LLM Calls: <strong style={{color: '#38bdf8'}}>{selectedTask.llm_call_count}</strong></div>
                      <div>Tokens: {selectedTask.token_usage?.total_tokens || 0} (Prompt: {selectedTask.token_usage?.prompt_tokens || 0}, Comp: {selectedTask.token_usage?.completion_tokens || 0})</div>
                    </div>
                  </div>

                  {selectedTask.result_summary && (
                    <div style={{background: 'rgba(56, 189, 248, 0.08)', border: '1px solid rgba(56, 189, 248, 0.3)', borderRadius: '8px', padding: '1rem', marginTop: '1.25rem'}}>
                      <div style={{fontSize: '0.85rem', textTransform: 'uppercase', color: '#38bdf8', fontWeight: 700}}>Final Verified Summary & Outcome:</div>
                      <div style={{fontSize: '0.95rem', color: '#fff', marginTop: '0.4rem', lineHeight: 1.5}}>{selectedTask.result_summary}</div>
                    </div>
                  )}
                </div>

                {/* Chronological Action History Timeline */}
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">🔍 Step-by-Step Execution Timeline ({selectedTask.steps?.length || 0} Steps)</div>
                    <span style={{fontSize: '0.8rem', color: '#94a3b8'}}>Independent Observation & Verification</span>
                  </div>

                  <div className="timeline">
                    {selectedTask.steps?.map(step => (
                      <div key={step.id} className="timeline-step">
                        <div className="step-num">{step.step_number}</div>
                        <div className="step-content">
                          <div className="step-header">
                            <div>
                              <span className="step-tool">{step.tool_name}</span>
                              <span style={{marginLeft: '0.75rem', fontSize: '0.75rem', color: '#94a3b8'}}>{step.created_at?.substring(11, 19)}</span>
                            </div>
                            <span className="badge" style={{background: step.status === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)', color: step.status === 'success' ? '#34d399' : '#f87171'}}>
                              {step.status}
                            </span>
                          </div>

                          <div style={{fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '0.4rem'}}>
                            Arguments: <code style={{fontFamily: 'monospace', color: '#a7f3d0'}}>{JSON.stringify(step.arguments)}</code>
                          </div>

                          <div className="step-obs">
                            <strong>Observation:</strong><br />
                            {step.observation}
                          </div>

                          {step.evidence_ref && (
                            <div style={{marginTop: '0.5rem', fontSize: '0.8rem', color: '#38bdf8'}}>
                              📸 Evidence Screenshot: <span style={{fontFamily: 'monospace', color: '#94a3b8'}}>{step.evidence_ref}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                    {(!selectedTask.steps || selectedTask.steps.length === 0) && (
                      <div style={{textAlign: 'center', color: '#94a3b8', padding: '2rem'}}>No execution steps recorded yet for this task.</div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'human_queue' && (
          <div className="card">
            <div className="card-header">
              <div className="card-title">🙋 Human-in-the-Loop Approval & Question Queue ({questions.length})</div>
              <span style={{fontSize: '0.8rem', color: '#94a3b8'}}>Task Pauses Safely Until Operator Answers</span>
            </div>

            <div>
              {questions.map(q => (
                <div key={q.id} style={{background: 'rgba(15, 23, 42, 0.8)', border: '1px solid #f59e0b', borderRadius: '8px', padding: '1.25rem', marginBottom: '1.25rem'}}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem'}}>
                    <span style={{fontFamily: 'monospace', color: '#f59e0b', fontWeight: 700}}>{q.id} (Task: {q.task_id})</span>
                    <span className="badge badge-awaiting_human">Needs Input</span>
                  </div>
                  <h4 style={{fontSize: '1.05rem', color: '#fff', marginBottom: '0.75rem'}}>{q.question_text}</h4>

                  {q.options && q.options.length > 0 && (
                    <div style={{display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap'}}>
                      {q.options.map((opt, idx) => (
                        <button key={idx} className="btn btn-secondary btn-sm" onClick={() => handleAnswerQuestion(q.id, opt)}>
                          Option: {opt}
                        </button>
                      ))}
                    </div>
                  )}

                  <div style={{display: 'flex', gap: '0.5rem', marginTop: '0.5rem'}}>
                    <input
                      type="text"
                      placeholder="Type custom human answer or instruction..."
                      value={humanAnswer[q.id] || ''}
                      onChange={e => setHumanAnswer({...humanAnswer, [q.id]: e.target.value})}
                    />
                    <button className="btn btn-primary" onClick={() => handleAnswerQuestion(q.id, humanAnswer[q.id])}>
                      Submit & Resume Task
                    </button>
                  </div>
                </div>
              ))}
              {questions.length === 0 && (
                <div style={{textAlign: 'center', color: '#94a3b8', padding: '3rem'}}>
                  ✅ No questions pending in the queue. All tasks proceeding autonomously within policy bounds.
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'scheduler' && (
          <div>
            <div className="card" style={{marginBottom: '1.5rem'}}>
              <div className="card-header">
                <div className="card-title">⏰ Payment Follow-up Scheduler Controls</div>
                <button className="btn btn-primary" onClick={handleTriggerScheduler}>⚡ Run Now (Force Run)</button>
              </div>
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', background: '#0a0e17', padding: '1rem', borderRadiu: '8px', fontSize: '0.85rem'}}>
                <div>
                  <span style={{color: '#94a3b8'}}>Timezone:</span>
                  <div style={{fontWeight: 700, color: '#fff'}}>{clockInfo?.timezone || 'Asia/Kolkata'}</div>
                </div>
                <div>
                  <span style={{color: '#94a3b8'}}>Business Hours Window:</span>
                  <div style={{fontWeight: 700, color: '#fff'}}>{clockInfo?.business_hours_start} - {clockInfo?.business_hours_end}</div>
                </div>
                <div>
                  <span style={{color: '#94a3b8'}}>Business Days:</span>
                  <div style={{fontWeight: 700, color: '#fff'}}>Mon - Fri (0-4)</div>
                </div>
                <div>
                  <span style={{color: '#94a3b8'}}>Single-Instance Lock:</span>
                  <div style={{fontWeight: 700, color: '#10b981'}}>Protected in SQLite</div>
                </div>
              </div>

              {/* Dev Clock Override */}
              <div style={{marginTop: '1.25rem', paddingTop: '1.25rem', borderTop: '1px solid var(--border-color)', display: 'flex', gap: '1rem', alignItems: 'center'}}>
                <span style={{fontSize: '0.85rem', color: '#94a3b8'}}>Dev Clock Override:</span>
                <input
                  type="text"
                  placeholder="e.g. 2026-10-15T10:30:00+05:30 (or leave empty to reset)"
                  style={{maxWidth: '350px'}}
                  value={clockOverrideInput}
                  onChange={e => setClockOverrideInput(e.target.value)}
                />
                <button className="btn btn-secondary btn-sm" onClick={handleSetClockOverride}>Set Override</button>
                <button className="btn btn-secondary btn-sm" onClick={() => { setClockOverrideInput(''); handleSetClockOverride(); }}>Reset to Real Time</button>
              </div>
            </div>

            {/* Run History */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">📜 Scheduler Run History ({schedulerRuns.length})</div>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Type</th>
                    <th>Started At</th>
                    <th>Status</th>
                    <th>Invoices Checked</th>
                    <th>Reminders Dispatched</th>
                  </tr>
                </thead>
                <tbody>
                  {schedulerRuns.map(r => (
                    <tr key={r.id}>
                      <td style={{fontFamily: 'monospace', color: '#38bdf8'}}>{r.id}</td>
                      <td>{r.run_type}</td>
                      <td>{r.started_at?.substring(0, 19)}</td>
                      <td><span className="badge badge-completed">{r.status}</span></td>
                      <td style={{fontWeight: 600}}>{r.invoices_checked}</td>
                      <td style={{fontWeight: 700, color: '#10b981'}}>{r.reminders_sent} sent</td>
                    </tr>
                  ))}
                  {schedulerRuns.length === 0 && (
                    <tr>
                      <td colSpan="6" style={{textAlign: 'center', padding: '2rem', color: '#94a3b8'}}>No runs yet. Click "Run Now" above to trigger a cycle.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'apps' && (
          <div className="grid-2">
            <div className="card">
              <div className="card-header">
                <div className="card-title">🏢 Simulated Company ERP</div>
                <a href={COMPANY_BASE} target="_blank" className="btn btn-secondary btn-sm">Open App &rarr;</a>
              </div>
              <p style={{fontSize: '0.9rem', color: '#94a3b8', marginBottom: '1.25rem'}}>
                Local server-rendered FastAPI app owning vendor directories, invoice records, and single-use upload links.
              </p>
              <div style={{background: '#0a0e17', padding: '1rem', borderRadius: '8px', fontSize: '0.85rem'}}>
                <div>URL: <strong>{COMPANY_BASE}</strong> (Port 8001)</div>
                <div style={{marginTop: '0.4rem'}}>Features: UI Perturbation Toggle, Fault Injection, Token-scoped Uploads</div>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <div className="card-title">📫 Email Sandbox</div>
                <a href={EMAIL_BASE} target="_blank" className="btn btn-secondary btn-sm">Open App &rarr;</a>
              </div>
              <p style={{fontSize: '0.9rem', color: '#94a3b8', marginBottom: '1.25rem'}}>
                Local server-rendered mailbox seeded with synthetic invoice attachments from Company X, Acme Corp, Beta Logistics, and outbox logs.
              </p>
              <div style={{background: '#0a0e17', padding: '1rem', borderRadius: '8px', fontSize: '0.85rem'}}>
                <div>URL: <strong>{EMAIL_BASE}</strong> (Port 8002)</div>
                <div style={{marginTop: '0.4rem'}}>Features: Idempotency Key Tracking, Isolated Sandbox, Never Delivers Real Mail</div>
              </div>
            </div>

            <div className="card" style={{gridColumn: '1 / -1'}}>
              <div className="card-header">
                <div className="card-title">🧹 Reset Test Fixtures to Clean Seed</div>
                <button className="btn btn-secondary btn-sm" onClick={async () => {
                  if (confirm('Reset ERP and Email databases to clean baseline state? All processed test bills will be wiped.')) {
                    await fetch(`${COMPANY_BASE}/api/reset-data`, { method: 'POST' });
                    await fetchData();
                    alert('Databases successfully reset to clean baseline! New bill tests are ready to run.');
                  }
                }}>Reset to Baseline (Removes processed bills)</button>
              </div>
              <p style={{fontSize: '0.9rem', color: '#94a3b8', margin: 0}}>
                Resets the ERP invoice register so that both Company X October invoice (INV-X-003) and Nova Tech invoice (NOV-2026-001) are treated as brand new, non-duplicate bills.
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));
