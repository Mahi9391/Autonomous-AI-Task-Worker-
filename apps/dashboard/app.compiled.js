const { useState, useEffect } = window.React;
const ReactDOM = window.ReactDOM;
const React = window.React;

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
        headers: {
          'Content-Type': 'application/json'
        },
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
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          answer
        })
      });
      fetchData();
    } catch (err) {
      alert('Error answering question: ' + err.message);
    }
  }
  async function handleTriggerScheduler() {
    try {
      const res = await fetch(`${API_BASE}/api/scheduler/run-now`, {
        method: 'POST'
      });
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
      await fetch(`${API_BASE}/api/tasks`, {
        method: 'DELETE'
      });
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
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          override_datetime: clockOverrideInput || null
        })
      });
      fetchData();
    } catch (err) {
      alert('Clock override error: ' + err.message);
    }
  }
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("header", null, /*#__PURE__*/React.createElement("div", {
    className: "header-container"
  }, /*#__PURE__*/React.createElement("div", {
    className: "logo-group"
  }, /*#__PURE__*/React.createElement("div", {
    className: "logo-icon"
  }, /*#__PURE__*/React.createElement("svg", {
    width: "20",
    height: "20",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#fff",
    strokeWidth: "2.5"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 6v6l4 2"
  }))), /*#__PURE__*/React.createElement("div", {
    className: "logo-text"
  }, "centrAlign ", /*#__PURE__*/React.createElement("span", null, "Autonomous Worker"))), /*#__PURE__*/React.createElement("div", {
    className: "nav-tabs"
  }, /*#__PURE__*/React.createElement("button", {
    className: `nav-tab ${activeTab === 'tasks' ? 'active' : ''}`,
    onClick: () => setActiveTab('tasks')
  }, "\uD83D\uDE80 Tasks & Launch"), /*#__PURE__*/React.createElement("button", {
    className: `nav-tab ${activeTab === 'task_detail' ? 'active' : ''}`,
    onClick: () => setActiveTab('task_detail')
  }, "\uD83D\uDD0D Inspector ", selectedTask ? `(${selectedTask.id})` : ''), /*#__PURE__*/React.createElement("button", {
    className: `nav-tab ${activeTab === 'human_queue' ? 'active' : ''}`,
    onClick: () => setActiveTab('human_queue')
  }, "\uD83D\uDE4B Human Queue ", questions.length > 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#f59e0b',
      fontWeight: 800
    }
  }, "(", questions.length, ")")), /*#__PURE__*/React.createElement("button", {
    className: `nav-tab ${activeTab === 'scheduler' ? 'active' : ''}`,
    onClick: () => setActiveTab('scheduler')
  }, "\u23F0 Follow-up Scheduler"), /*#__PURE__*/React.createElement("button", {
    className: `nav-tab ${activeTab === 'apps' ? 'active' : ''}`,
    onClick: () => setActiveTab('apps')
  }, "\uD83C\uDFE2 Apps & Controls")), /*#__PURE__*/React.createElement("div", {
    className: "dev-clock-widget"
  }, /*#__PURE__*/React.createElement("div", {
    className: "clock-display",
    title: "System Injectable Clock"
  }, /*#__PURE__*/React.createElement("span", {
    className: `status-dot ${clockInfo?.is_business_hours ? '' : 'inactive'}`
  }), /*#__PURE__*/React.createElement("span", null, clockInfo?.current_time ? clockInfo.current_time.substring(11, 19) : '--:--:--'), /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#94a3b8',
      fontSize: '0.75rem'
    }
  }, clockInfo?.is_business_hours ? 'BIZ HOURS' : 'AFTER HOURS'))))), /*#__PURE__*/React.createElement("main", null, activeTab === 'tasks' && /*#__PURE__*/React.createElement("div", {
    className: "grid-2"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\u2728 Submit Autonomous Task"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.8rem',
      color: '#94a3b8'
    }
  }, "Single-Agent Runtime")), /*#__PURE__*/React.createElement("form", {
    onSubmit: handleCreateTask
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: '1rem'
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      fontSize: '0.85rem',
      color: '#94a3b8',
      marginBottom: '0.4rem'
    }
  }, "Workflow Configuration:"), /*#__PURE__*/React.createElement("select", {
    value: taskWorkflow,
    onChange: e => setTaskWorkflow(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "invoice_processing"
  }, "Workflow A: Accounts Payable Invoice Processing"), /*#__PURE__*/React.createElement("option", {
    value: "scheduled_payment_followup"
  }, "Workflow B: Scheduled Payment Follow-up"), /*#__PURE__*/React.createElement("option", {
    value: "vendor_summary_report"
  }, "Workflow C (Generalization): Vendor Balance Audit Report"))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: '1.25rem'
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      fontSize: '0.85rem',
      color: '#94a3b8',
      marginBottom: '0.4rem'
    }
  }, "Natural Language Goal / Instruction:"), /*#__PURE__*/React.createElement("textarea", {
    rows: "4",
    value: taskGoal,
    onChange: e => setTaskGoal(e.target.value),
    required: true,
    placeholder: "Type natural language instructions..."
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '0.5rem',
      marginBottom: '1.25rem',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.8rem',
      color: '#94a3b8',
      width: '100%'
    }
  }, "Quick Presets:"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn btn-secondary btn-sm",
    onClick: () => {
      setTaskWorkflow('invoice_processing');
      setTaskGoal('Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.');
    }
  }, "Target Challenge: Latest Company X Invoice"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn btn-secondary btn-sm",
    onClick: () => {
      setTaskWorkflow('invoice_processing');
      setTaskGoal('Find the new invoice from Nova Tech, extract the amount and due date, enter it into our internal system, and tell me once it is done.');
    }
  }, "Brand New Bill: Nova Tech ($3,450)"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn btn-secondary btn-sm",
    onClick: () => {
      setTaskWorkflow('scheduled_payment_followup');
      setTaskGoal('Audit overdue invoices, check business hour eligibility, and dispatch reminders with idempotency verification.');
    }
  }, "Payment Follow-up Audit"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn btn-secondary btn-sm",
    onClick: () => {
      setTaskWorkflow('vendor_summary_report');
      setTaskGoal('Audit all invoices for vendor Company X, calculate total settled versus outstanding balances, and compile an audit summary.');
    }
  }, "Generalization: Vendor Summary")), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    className: "btn btn-primary",
    style: {
      width: '100%'
    },
    disabled: isSubmitting
  }, isSubmitting ? 'Dispatching...' : '🚀 Launch Autonomous Task'))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\uD83D\uDCDC Execution Tasks (", tasks.length, ")"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '0.5rem'
    }
  }, tasks.length > 0 && /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    style: {
      color: '#f87171',
      borderColor: '#ef444455'
    },
    onClick: handleClearTasks
  }, "\uD83D\uDDD1 Clear History"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    onClick: fetchData
  }, "\u21BB Refresh"))), /*#__PURE__*/React.createElement("div", {
    style: {
      maxHeight: '520px',
      overflowY: 'auto'
    }
  }, tasks.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    className: `task-item ${selectedTask?.id === t.id ? 'selected' : ''}`,
    onClick: async () => {
      const sRes = await fetch(`${API_BASE}/api/tasks/${t.id}`);
      setSelectedTask(await sRes.json());
      setActiveTab('task_detail');
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '0.4rem'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'monospace',
      fontWeight: 700,
      color: '#38bdf8'
    }
  }, t.id), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '0.5rem'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `badge badge-${t.status}`
  }, t.status), /*#__PURE__*/React.createElement("button", {
    style: {
      background: 'transparent',
      border: 'none',
      color: '#94a3b8',
      cursor: 'pointer',
      fontSize: '0.9rem',
      padding: '0 4px',
      lineHeight: 1
    },
    title: "Remove this task",
    onClick: async e => {
      e.stopPropagation();
      await fetch(`${API_BASE}/api/tasks/${t.id}`, {
        method: 'DELETE'
      });
      if (selectedTask?.id === t.id) setSelectedTask(null);
      fetchData();
    }
  }, "\u2715"))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.9rem',
      color: '#f8fafc',
      fontWeight: 500,
      marginBottom: '0.5rem'
    }
  }, t.goal), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      fontSize: '0.78rem',
      color: '#94a3b8'
    }
  }, /*#__PURE__*/React.createElement("span", null, "Steps: ", t.step_count, " | LLM Calls: ", t.llm_call_count), /*#__PURE__*/React.createElement("span", null, t.created_at?.substring(11, 19))))), tasks.length === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'center',
      color: '#94a3b8',
      padding: '3rem'
    }
  }, "No tasks executed yet. Submit a task above.")))), activeTab === 'task_detail' && /*#__PURE__*/React.createElement("div", null, !selectedTask ? /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      textAlign: 'center',
      padding: '4rem',
      color: '#94a3b8'
    }
  }, /*#__PURE__*/React.createElement("h3", null, "No Task Selected"), /*#__PURE__*/React.createElement("p", {
    style: {
      marginTop: '0.5rem'
    }
  }, "Select a task from the Tasks tab to view its step-by-step action history and verification evidence."), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    style: {
      marginTop: '1.5rem'
    },
    onClick: () => setActiveTab('tasks')
  }, "Go to Tasks")) : /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: '1.5rem'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      flexWrap: 'wrap',
      gap: '1rem'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '0.75rem'
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: '1.4rem',
      fontWeight: 800
    }
  }, selectedTask.id), /*#__PURE__*/React.createElement("span", {
    className: `badge badge-${selectedTask.status}`
  }, selectedTask.status)), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '1rem',
      color: '#cbd5e1',
      marginTop: '0.35rem'
    }
  }, selectedTask.goal)), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'right',
      fontSize: '0.85rem',
      color: '#94a3b8'
    }
  }, /*#__PURE__*/React.createElement("div", null, "Workflow: ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: '#fff'
    }
  }, selectedTask.workflow_id)), /*#__PURE__*/React.createElement("div", null, "Total Steps: ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: '#38bdf8'
    }
  }, selectedTask.step_count), " | LLM Calls: ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: '#38bdf8'
    }
  }, selectedTask.llm_call_count)), /*#__PURE__*/React.createElement("div", null, "Tokens: ", selectedTask.token_usage?.total_tokens || 0, " (Prompt: ", selectedTask.token_usage?.prompt_tokens || 0, ", Comp: ", selectedTask.token_usage?.completion_tokens || 0, ")"))), selectedTask.result_summary && /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'rgba(56, 189, 248, 0.08)',
      border: '1px solid rgba(56, 189, 248, 0.3)',
      borderRadius: '8px',
      padding: '1rem',
      marginTop: '1.25rem'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.85rem',
      textTransform: 'uppercase',
      color: '#38bdf8',
      fontWeight: 700
    }
  }, "Final Verified Summary & Outcome:"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.95rem',
      color: '#fff',
      marginTop: '0.4rem',
      lineHeight: 1.5
    }
  }, selectedTask.result_summary))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\uD83D\uDD0D Step-by-Step Execution Timeline (", selectedTask.steps?.length || 0, " Steps)"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.8rem',
      color: '#94a3b8'
    }
  }, "Independent Observation & Verification")), /*#__PURE__*/React.createElement("div", {
    className: "timeline"
  }, selectedTask.steps?.map(step => /*#__PURE__*/React.createElement("div", {
    key: step.id,
    className: "timeline-step"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-num"
  }, step.step_number), /*#__PURE__*/React.createElement("div", {
    className: "step-content"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
    className: "step-tool"
  }, step.tool_name), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: '0.75rem',
      fontSize: '0.75rem',
      color: '#94a3b8'
    }
  }, step.created_at?.substring(11, 19))), /*#__PURE__*/React.createElement("span", {
    className: "badge",
    style: {
      background: step.status === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
      color: step.status === 'success' ? '#34d399' : '#f87171'
    }
  }, step.status)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.8rem',
      color: '#cbd5e1',
      marginBottom: '0.4rem'
    }
  }, "Arguments: ", /*#__PURE__*/React.createElement("code", {
    style: {
      fontFamily: 'monospace',
      color: '#a7f3d0'
    }
  }, JSON.stringify(step.arguments))), /*#__PURE__*/React.createElement("div", {
    className: "step-obs"
  }, /*#__PURE__*/React.createElement("strong", null, "Observation:"), /*#__PURE__*/React.createElement("br", null), step.observation), step.evidence_ref && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '0.5rem',
      fontSize: '0.8rem',
      color: '#38bdf8'
    }
  }, "\uD83D\uDCF8 Evidence Screenshot: ", /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'monospace',
      color: '#94a3b8'
    }
  }, step.evidence_ref))))), (!selectedTask.steps || selectedTask.steps.length === 0) && /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'center',
      color: '#94a3b8',
      padding: '2rem'
    }
  }, "No execution steps recorded yet for this task."))))), activeTab === 'human_queue' && /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\uD83D\uDE4B Human-in-the-Loop Approval & Question Queue (", questions.length, ")"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.8rem',
      color: '#94a3b8'
    }
  }, "Task Pauses Safely Until Operator Answers")), /*#__PURE__*/React.createElement("div", null, questions.map(q => /*#__PURE__*/React.createElement("div", {
    key: q.id,
    style: {
      background: 'rgba(15, 23, 42, 0.8)',
      border: '1px solid #f59e0b',
      borderRadius: '8px',
      padding: '1.25rem',
      marginBottom: '1.25rem'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '0.5rem'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'monospace',
      color: '#f59e0b',
      fontWeight: 700
    }
  }, q.id, " (Task: ", q.task_id, ")"), /*#__PURE__*/React.createElement("span", {
    className: "badge badge-awaiting_human"
  }, "Needs Input")), /*#__PURE__*/React.createElement("h4", {
    style: {
      fontSize: '1.05rem',
      color: '#fff',
      marginBottom: '0.75rem'
    }
  }, q.question_text), q.options && q.options.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '0.5rem',
      marginBottom: '1rem',
      flexWrap: 'wrap'
    }
  }, q.options.map((opt, idx) => /*#__PURE__*/React.createElement("button", {
    key: idx,
    className: "btn btn-secondary btn-sm",
    onClick: () => handleAnswerQuestion(q.id, opt)
  }, "Option: ", opt))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '0.5rem',
      marginTop: '0.5rem'
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "text",
    placeholder: "Type custom human answer or instruction...",
    value: humanAnswer[q.id] || '',
    onChange: e => setHumanAnswer({
      ...humanAnswer,
      [q.id]: e.target.value
    })
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: () => handleAnswerQuestion(q.id, humanAnswer[q.id])
  }, "Submit & Resume Task")))), questions.length === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'center',
      color: '#94a3b8',
      padding: '3rem'
    }
  }, "\u2705 No questions pending in the queue. All tasks proceeding autonomously within policy bounds."))), activeTab === 'scheduler' && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: '1.5rem'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\u23F0 Payment Follow-up Scheduler Controls"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: handleTriggerScheduler
  }, "\u26A1 Run Now (Force Run)")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: '1rem',
      background: '#0a0e17',
      padding: '1rem',
      borderRadiu: '8px',
      fontSize: '0.85rem'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#94a3b8'
    }
  }, "Timezone:"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700,
      color: '#fff'
    }
  }, clockInfo?.timezone || 'Asia/Kolkata')), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#94a3b8'
    }
  }, "Business Hours Window:"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700,
      color: '#fff'
    }
  }, clockInfo?.business_hours_start, " - ", clockInfo?.business_hours_end)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#94a3b8'
    }
  }, "Business Days:"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700,
      color: '#fff'
    }
  }, "Mon - Fri (0-4)")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#94a3b8'
    }
  }, "Single-Instance Lock:"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700,
      color: '#10b981'
    }
  }, "Protected in SQLite"))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '1.25rem',
      paddingTop: '1.25rem',
      borderTop: '1px solid var(--border-color)',
      display: 'flex',
      gap: '1rem',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.85rem',
      color: '#94a3b8'
    }
  }, "Dev Clock Override:"), /*#__PURE__*/React.createElement("input", {
    type: "text",
    placeholder: "e.g. 2026-10-15T10:30:00+05:30 (or leave empty to reset)",
    style: {
      maxWidth: '350px'
    },
    value: clockOverrideInput,
    onChange: e => setClockOverrideInput(e.target.value)
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    onClick: handleSetClockOverride
  }, "Set Override"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    onClick: () => {
      setClockOverrideInput('');
      handleSetClockOverride();
    }
  }, "Reset to Real Time"))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\uD83D\uDCDC Scheduler Run History (", schedulerRuns.length, ")")), /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Run ID"), /*#__PURE__*/React.createElement("th", null, "Type"), /*#__PURE__*/React.createElement("th", null, "Started At"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", null, "Invoices Checked"), /*#__PURE__*/React.createElement("th", null, "Reminders Dispatched"))), /*#__PURE__*/React.createElement("tbody", null, schedulerRuns.map(r => /*#__PURE__*/React.createElement("tr", {
    key: r.id
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      fontFamily: 'monospace',
      color: '#38bdf8'
    }
  }, r.id), /*#__PURE__*/React.createElement("td", null, r.run_type), /*#__PURE__*/React.createElement("td", null, r.started_at?.substring(0, 19)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
    className: "badge badge-completed"
  }, r.status)), /*#__PURE__*/React.createElement("td", {
    style: {
      fontWeight: 600
    }
  }, r.invoices_checked), /*#__PURE__*/React.createElement("td", {
    style: {
      fontWeight: 700,
      color: '#10b981'
    }
  }, r.reminders_sent, " sent"))), schedulerRuns.length === 0 && /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: "6",
    style: {
      textAlign: 'center',
      padding: '2rem',
      color: '#94a3b8'
    }
  }, "No runs yet. Click \"Run Now\" above to trigger a cycle.")))))), activeTab === 'apps' && /*#__PURE__*/React.createElement("div", {
    className: "grid-2"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\uD83C\uDFE2 Simulated Company ERP"), /*#__PURE__*/React.createElement("a", {
    href: COMPANY_BASE,
    target: "_blank",
    className: "btn btn-secondary btn-sm"
  }, "Open App \u2192")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '0.9rem',
      color: '#94a3b8',
      marginBottom: '1.25rem'
    }
  }, "Local server-rendered FastAPI app owning vendor directories, invoice records, and single-use upload links."), /*#__PURE__*/React.createElement("div", {
    style: {
      background: '#0a0e17',
      padding: '1rem',
      borderRadius: '8px',
      fontSize: '0.85rem'
    }
  }, /*#__PURE__*/React.createElement("div", null, "URL: ", /*#__PURE__*/React.createElement("strong", null, COMPANY_BASE), " (Port 8001)"), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '0.4rem'
    }
  }, "Features: UI Perturbation Toggle, Fault Injection, Token-scoped Uploads"))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\uD83D\uDCEB Email Sandbox"), /*#__PURE__*/React.createElement("a", {
    href: EMAIL_BASE,
    target: "_blank",
    className: "btn btn-secondary btn-sm"
  }, "Open App \u2192")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '0.9rem',
      color: '#94a3b8',
      marginBottom: '1.25rem'
    }
  }, "Local server-rendered mailbox seeded with synthetic invoice attachments from Company X, Acme Corp, Beta Logistics, and outbox logs."), /*#__PURE__*/React.createElement("div", {
    style: {
      background: '#0a0e17',
      padding: '1rem',
      borderRadius: '8px',
      fontSize: '0.85rem'
    }
  }, /*#__PURE__*/React.createElement("div", null, "URL: ", /*#__PURE__*/React.createElement("strong", null, EMAIL_BASE), " (Port 8002)"), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '0.4rem'
    }
  }, "Features: Idempotency Key Tracking, Isolated Sandbox, Never Delivers Real Mail"))), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      gridColumn: '1 / -1'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, "\uD83E\uDDF9 Reset Test Fixtures to Clean Seed"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    onClick: async () => {
      if (confirm('Reset ERP and Email databases to clean baseline state? All processed test bills will be wiped.')) {
        await fetch(`${COMPANY_BASE}/api/reset-data`, {
          method: 'POST'
        });
        await fetchData();
        alert('Databases successfully reset to clean baseline! New bill tests are ready to run.');
      }
    }
  }, "Reset to Baseline (Removes processed bills)")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '0.9rem',
      color: '#94a3b8',
      margin: 0
    }
  }, "Resets the ERP invoice register so that both Company X October invoice (INV-X-003) and Nova Tech invoice (NOV-2026-001) are treated as brand new, non-duplicate bills.")))));
}
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));