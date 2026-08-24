import { useState, useEffect, useRef } from 'react';
import {
  ChevronRight, Activity, FileText, Calendar,
  AlertCircle, CheckCircle, Clock, Plus, Trash2, Eye
} from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import Modal from '../components/Modal';

const TODAY = new Date().toISOString().split('T')[0];

const EMPTY_RX = { name: '', dosage: '', frequency: 'twice_daily', duration_days: 7 };
const FREQUENCY_OPTS = [
  { value: 'once_daily', label: 'Once daily' },
  { value: 'twice_daily', label: 'Twice daily' },
  { value: 'three_times_daily', label: 'Three times daily' },
  { value: 'four_times_daily', label: 'Four times daily' },
  { value: 'as_needed', label: 'As needed' },
  { value: 'weekly', label: 'Weekly' },
];

function TierBadge({ tier }) {
  const cls = {
    emergency: 'badge-emergency',
    priority: 'badge-priority',
    anchor: 'badge-anchor',
    regular: 'badge-regular',
  }[tier] || 'badge-neutral';
  return <span className={`badge ${cls}`}>{tier}</span>;
}

function StatusBadge({ status }) {
  const map = {
    waiting: 'badge-neutral',
    in_progress: 'badge-warning',
    completed: 'badge-success',
    cancelled: 'badge-danger',
    leave_cancelled: 'badge-danger',
  };
  return <span className={`badge ${map[status] || 'badge-neutral'}`}>{status?.replace('_', ' ')}</span>;
}

export default function DoctorDashboard({ onToast }) {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('queue');

  // Doctor setup
  const [doctorId, setDoctorId] = useState(() => {
    return (user?.role === 'doctor' && user?.id) ? String(user.id) : (localStorage.getItem('hq_doctor_id') || '2');
  });
  const [session, setSession] = useState('morning');
  const [date, setDate] = useState(TODAY);

  // Leave Management State
  const TOMORROW = new Date(Date.now() + 86400000).toISOString().split('T')[0];
  const [leaveForm, setLeaveForm] = useState({ start_date: TOMORROW, end_date: TOMORROW, reason: 'Annual Leave / CME Training' });
  const [leaveSubmitting, setLeaveSubmitting] = useState(false);
  const [leaveResult, setLeaveResult] = useState(null);

  // Queue
  const [queue, setQueue] = useState([]);
  const [loadingQueue, setLoadingQueue] = useState(false);
  const [callingNext, setCallingNext] = useState(false);
  const [completingId, setCompletingId] = useState(null);

  // Triage modal
  const [triageModal, setTriageModal] = useState(null); // { queueId, data }
  const [loadingTriage, setLoadingTriage] = useState(false);

  // Post-visit modal
  const [noteModal, setNoteModal] = useState(null); // { queueId }
  const [rawNotes, setRawNotes] = useState('');
  const [rxRows, setRxRows] = useState([{ ...EMPTY_RX }]);
  const [submittingNotes, setSubmittingNotes] = useState(false);

  const pollRef = useRef(null);

  useEffect(() => {
    if (user?.role === 'doctor' && user?.id) {
      setDoctorId(String(user.id));
      localStorage.setItem('hq_doctor_id', String(user.id));
    }
  }, [user]);

  const fetchQueue = () => {
    if (!doctorId) return;
    setLoadingQueue(true);
    api.queue.list(doctorId, date)
      .then(setQueue)
      .catch(() => setQueue([]))
      .finally(() => setLoadingQueue(false));
  };

  useEffect(() => {
    if (activeTab === 'queue' && doctorId) {
      fetchQueue();
      pollRef.current = setInterval(fetchQueue, 15000);
    }
    return () => clearInterval(pollRef.current);
  }, [activeTab, doctorId, date, session]);

  const handleCallNext = async () => {
    if (!doctorId) { onToast('warning', 'Set Doctor ID', 'Enter your Doctor ID in the filters.'); return; }
    setCallingNext(true);
    try {
      const next = await api.queue.callNext(doctorId, session);
      onToast('success', 'Called next patient', `Token #${next?.token_number} — ${next?.tier} tier`);
      fetchQueue();
    } catch (err) {
      onToast('error', 'Failed to call next', err.message);
    } finally {
      setCallingNext(false);
    }
  };

  const handleComplete = async (queueId) => {
    setCompletingId(queueId);
    try {
      await api.queue.complete(queueId);
      onToast('success', 'Consultation complete', 'Token marked as completed.');
      fetchQueue();
    } catch (err) {
      onToast('error', 'Failed to complete', err.message);
    } finally {
      setCompletingId(null);
    }
  };

  const handleApplyLeave = async () => {
    if (!doctorId) { onToast('warning', 'Set Doctor ID', 'Doctor ID is required.'); return; }
    if (!leaveForm.start_date || !leaveForm.end_date) {
      onToast('warning', 'Select Dates', 'Please select leave start and end dates.');
      return;
    }
    setLeaveSubmitting(true);
    setLeaveResult(null);
    try {
      const res = await api.doctors.addLeave(doctorId, {
        start_date: leaveForm.start_date,
        end_date: leaveForm.end_date,
        reason: leaveForm.reason || 'Doctor Leave of Absence',
      });
      setLeaveResult(res);
      onToast('success', 'Leave recorded!', `${res.cancelled_appointments || 0} conflicting appointments cancelled.`);
      fetchQueue();
    } catch (err) {
      onToast('error', 'Leave request failed', err.message);
    } finally {
      setLeaveSubmitting(false);
    }
  };

  const handleViewTriage = async (queueId) => {
    setLoadingTriage(true);
    setTriageModal({ queueId, data: null });
    try {
      const data = await api.clinical.getSymptoms(queueId);
      setTriageModal({ queueId, data });
    } catch {
      setTriageModal({ queueId, data: null, error: 'No triage data found for this patient.' });
    } finally {
      setLoadingTriage(false);
    }
  };

  const handleOpenNotes = (queueId) => {
    setNoteModal({ queueId });
    setRawNotes('');
    setRxRows([{ ...EMPTY_RX }]);
  };

  const handleSubmitNotes = async () => {
    if (!rawNotes.trim()) { onToast('warning', 'Enter notes', 'Please enter clinical notes.'); return; }
    setSubmittingNotes(true);
    try {
      await api.clinical.submitNotes(noteModal.queueId, {
        raw_notes: rawNotes,
        medications: rxRows.filter(r => r.name.trim()),
      });
      onToast('success', 'Notes submitted', 'Post-visit summary will be generated by AI.');
      setNoteModal(null);
      fetchQueue();
    } catch (err) {
      onToast('error', 'Submission failed', err.message);
    } finally {
      setSubmittingNotes(false);
    }
  };

  const addRxRow = () => setRxRows(r => [...r, { ...EMPTY_RX }]);
  const removeRxRow = (i) => setRxRows(r => r.filter((_, idx) => idx !== i));
  const updateRxRow = (i, field, val) => setRxRows(r => r.map((row, idx) => idx === i ? { ...row, [field]: val } : row));

  const currentPatient = queue.find(q => q.status === 'in_progress');

  const tabs = [
    { id: 'queue', label: 'Live Queue', icon: <Activity size={15} /> },
    { id: 'schedule', label: 'My Schedule', icon: <Calendar size={15} /> },
    { id: 'leave', label: 'Doctor Leave & Off-Duty', icon: <Clock size={15} /> },
  ];

  return (
    <div>
      <div className="section-header">
        <div>
          <h2 className="section-title">Doctor Dashboard</h2>
          <p className="section-subtitle">Manage your patient queue and post-visit documentation</p>
        </div>
        <button
          id="call-next-btn"
          className="btn btn-primary btn-lg"
          onClick={handleCallNext}
          disabled={callingNext}
        >
          {callingNext ? <><span className="spinner spinner-sm" /> Calling…</> : <><ChevronRight size={18} /> Call Next Patient</>}
        </button>
      </div>

      <div className="page-tabs">
        {tabs.map(t => (
          <button key={t.id} className={`page-tab ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="card card-pad mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="form-group" style={{ margin: 0, minWidth: 140 }}>
            <label className="form-label">Doctor ID</label>
            <input
              id="doctor-id-input"
              className="form-input"
              type="number"
              placeholder="e.g. 1"
              value={doctorId}
              onChange={e => { setDoctorId(e.target.value); localStorage.setItem('hq_doctor_id', e.target.value); }}
            />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">Date</label>
            <input className="form-input" type="date" value={date} onChange={e => setDate(e.target.value)} />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">Session</label>
            <select className="form-select" value={session} onChange={e => setSession(e.target.value)} style={{ minWidth: 130 }}>
              <option value="morning">Morning</option>
              <option value="evening">Evening</option>
            </select>
          </div>
          <button className="btn btn-secondary" style={{ alignSelf: 'flex-end' }} onClick={fetchQueue} disabled={!doctorId}>
            <Activity size={15} /> Refresh
          </button>
        </div>
      </div>

      {/* ===== QUEUE TAB ===== */}
      {activeTab === 'queue' && (
        <div className="grid-main-side">
          <div>
            {loadingQueue ? (
              <div className="loading-overlay"><span className="spinner" /> Loading queue…</div>
            ) : queue.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon"><Activity size={40} /></div>
                <h3>Queue is empty</h3>
                <p>No patients in the queue for {date} {session} session.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {queue.map((entry) => (
                  <div key={entry.id} className={`queue-card ${entry.status === 'in_progress' ? 'current' : ''}`}>
                    <div className={`queue-token ${entry.tier}`}>
                      #{entry.token_number}
                    </div>
                    <div className="queue-info">
                      <div className="queue-patient-name">Patient #{entry.patient_id}</div>
                      <div className="queue-meta">
                        <TierBadge tier={entry.tier} />
                        <StatusBadge status={entry.status} />
                        <span className="queue-position">Pos: {entry.display_position}</span>
                        {entry.slot_type && <span className="badge badge-neutral">{entry.slot_type}</span>}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        className="btn btn-ghost btn-sm btn-icon"
                        onClick={() => handleViewTriage(entry.id)}
                        title="View AI Triage Brief"
                      >
                        <Eye size={15} />
                      </button>
                      {entry.status === 'in_progress' && (
                        <>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleOpenNotes(entry.id)}
                          >
                            <FileText size={14} /> Notes
                          </button>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => handleComplete(entry.id)}
                            disabled={completingId === entry.id}
                          >
                            {completingId === entry.id ? <span className="spinner spinner-sm" /> : <CheckCircle size={14} />}
                            Complete
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="flex flex-col gap-4">
            <div className="stat-card">
              <div className="stat-card-icon"><Activity size={20} color="var(--primary)" /></div>
              <div className="stat-card-label">Total in Queue</div>
              <div className="stat-card-value">{queue.length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-icon"><AlertCircle size={20} color="var(--tier-emergency)" /></div>
              <div className="stat-card-label">Emergency Patients</div>
              <div className="stat-card-value">{queue.filter(q => q.tier === 'emergency').length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-icon"><CheckCircle size={20} color="var(--success)" /></div>
              <div className="stat-card-label">Completed Today</div>
              <div className="stat-card-value">{queue.filter(q => q.status === 'completed').length}</div>
            </div>
            {currentPatient && (
              <div className="card card-pad" style={{ background: 'var(--primary-soft)', borderColor: 'var(--primary)' }}>
                <div className="text-sm font-600 mb-2" style={{ color: 'var(--primary)' }}>Currently Serving</div>
                <div className="font-700" style={{ fontSize: 'var(--text-2xl)' }}>#{currentPatient.token_number}</div>
                <TierBadge tier={currentPatient.tier} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== SCHEDULE TAB ===== */}
      {activeTab === 'schedule' && (
        <div className="card card-pad">
          <h3 className="font-600 mb-4">Today's Appointment Schedule</h3>
          {queue.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon"><Calendar size={40} /></div>
              <h3>No appointments</h3>
              <p>No appointments scheduled for the selected date and session.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Token</th>
                    <th>Position</th>
                    <th>Patient</th>
                    <th>Tier</th>
                    <th>Slot Type</th>
                    <th>Status</th>
                    <th>Booked At</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map(entry => (
                    <tr key={entry.id}>
                      <td className="font-700">#{entry.token_number}</td>
                      <td>{entry.display_position}</td>
                      <td>Patient #{entry.patient_id}</td>
                      <td><TierBadge tier={entry.tier} /></td>
                      <td><span className="badge badge-neutral">{entry.slot_type}</span></td>
                      <td><StatusBadge status={entry.status} /></td>
                      <td className="text-muted">{entry.booked_at ? new Date(entry.booked_at).toLocaleTimeString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ===== LEAVE & OFF-DUTY TAB ===== */}
      {activeTab === 'leave' && (
        <div style={{ maxWidth: 680, margin: '0 auto' }} className="flex flex-col gap-4">
          <div className="card card-pad">
            <h3 className="font-700 mb-1" style={{ fontSize: 'var(--text-lg)' }}>Record Doctor Leave of Absence</h3>
            <p className="text-sm text-secondary mb-4">
              Schedule off-duty dates. The conflict resolution engine will automatically cancel all overlapping appointments and enqueue real-time notifications to affected patients.
            </p>

            <div className="flex flex-col gap-4">
              <div className="grid-2">
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Leave Start Date</label>
                  <input
                    id="leave-start-date"
                    className="form-input"
                    type="date"
                    min={TODAY}
                    value={leaveForm.start_date}
                    onChange={e => setLeaveForm(f => ({ ...f, start_date: e.target.value }))}
                  />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Leave End Date</label>
                  <input
                    id="leave-end-date"
                    className="form-input"
                    type="date"
                    min={leaveForm.start_date || TODAY}
                    value={leaveForm.end_date}
                    onChange={e => setLeaveForm(f => ({ ...f, end_date: e.target.value }))}
                  />
                </div>
              </div>

              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label">Reason for Absence</label>
                <input
                  id="leave-reason"
                  className="form-input"
                  placeholder="e.g. Medical Conference / Annual Leave / CME Training"
                  value={leaveForm.reason}
                  onChange={e => setLeaveForm(f => ({ ...f, reason: e.target.value }))}
                />
              </div>

              <button
                id="submit-leave-btn"
                className="btn btn-primary btn-lg w-full"
                onClick={handleApplyLeave}
                disabled={leaveSubmitting || !doctorId}
              >
                {leaveSubmitting ? <><span className="spinner spinner-sm" /> Processing Conflict Resolution…</> : 'Apply Leave & Auto-Cancel Overlapping Appointments'}
              </button>
            </div>
          </div>

          {leaveResult && (
            <div className="info-banner success">
              <CheckCircle size={20} style={{ flexShrink: 0, marginTop: 2 }} />
              <div>
                <strong style={{ fontSize: 'var(--text-base)' }}>Doctor Leave Confirmed (ID #{leaveResult.leave_id})</strong>
                <div className="text-sm mt-1">
                  <strong>{leaveResult.cancelled_appointments || 0}</strong> overlapping appointment(s) were automatically cancelled.
                </div>
                <div className="text-xs text-muted mt-1">
                  Enqueued {leaveResult.notifications_queued || 0} patient cancellation alerts via WhatsApp & Email.
                </div>
              </div>
            </div>
          )}

          <div className="card card-pad" style={{ background: 'var(--bg-hover, rgba(255,255,255,0.02))' }}>
            <div className="text-xs font-600 text-muted uppercase tracking-wider mb-2">How Conflict Resolution Operates</div>
            <ul className="flex flex-col gap-2" style={{ paddingLeft: 18, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              <li>Scans all pending and waiting tokens for Doctor #{doctorId} across the selected dates.</li>
              <li>Atomically transitions all affected queue records from <code>waiting</code> to <code>cancelled</code>.</li>
              <li>Dispatches real-time WhatsApp delay/reschedule alerts and formal Email cancellation records to each patient.</li>
              <li>Frees up queue slots and removes pending appointments from live doctor queue.</li>
            </ul>
          </div>
        </div>
      )}

      {/* ===== TRIAGE MODAL ===== */}
      {triageModal && (
        <Modal
          title="AI Pre-Visit Triage Brief"
          subtitle={`Queue entry #${triageModal.queueId}`}
          onClose={() => setTriageModal(null)}
          footer={<button className="btn btn-secondary" onClick={() => setTriageModal(null)}>Close</button>}
        >
          {loadingTriage && <div className="loading-overlay"><span className="spinner" /> Loading triage data…</div>}
          {triageModal.error && (
            <div className="info-banner warning">
              <AlertCircle size={16} style={{ flexShrink: 0 }} />
              <span>{triageModal.error}</span>
            </div>
          )}
          {triageModal.data && (
            <div className="triage-panel">
              <div className="triage-row">
                <span className="triage-row-label">Urgency</span>
                <span className={`badge badge-${triageModal.data.urgency_level === 'critical' || triageModal.data.urgency_level === 'high' ? 'emergency' : triageModal.data.urgency_level === 'medium' ? 'priority' : 'regular'}`}>
                  {triageModal.data.urgency_level?.toUpperCase()}
                </span>
              </div>
              <div className="triage-row">
                <span className="triage-row-label">Chief Complaint</span>
                <span className="triage-row-value">{triageModal.data.chief_complaint || '—'}</span>
              </div>
              <div className="triage-row">
                <span className="triage-row-label">AI Summary</span>
                <span className="triage-row-value">{triageModal.data.ai_summary || triageModal.data.symptom_text}</span>
              </div>
              {triageModal.data.suggested_questions?.length > 0 && (
                <div className="triage-row">
                  <span className="triage-row-label">Ask Patient</span>
                  <ul className="triage-questions">
                    {triageModal.data.suggested_questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </Modal>
      )}

      {/* ===== POST-VISIT NOTES MODAL ===== */}
      {noteModal && (
        <Modal
          title="Post-Visit Notes & Prescription"
          subtitle={`Queue entry #${noteModal.queueId}`}
          onClose={() => setNoteModal(null)}
          size="modal-lg"
          footer={
            <>
              <button className="btn btn-secondary" onClick={() => setNoteModal(null)}>Cancel</button>
              <button
                id="submit-notes-btn"
                className="btn btn-primary"
                onClick={handleSubmitNotes}
                disabled={submittingNotes}
              >
                {submittingNotes ? <><span className="spinner spinner-sm" /> Submitting…</> : 'Submit Notes & Generate AI Summary'}
              </button>
            </>
          }
        >
          <div className="form-group">
            <label className="form-label">Clinical Notes</label>
            <textarea
              id="clinical-notes-textarea"
              className="form-textarea"
              style={{ minHeight: 120 }}
              value={rawNotes}
              onChange={e => setRawNotes(e.target.value)}
              placeholder="Enter your clinical observations, diagnosis, and treatment plan…"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="form-label" style={{ margin: 0 }}>Prescription</label>
            </div>
            <div className="rx-row-head">
              <span>Medication</span><span>Dosage</span><span>Frequency</span><span>Duration (days)</span><span></span>
            </div>
            <div className="flex flex-col gap-2 mt-2">
              {rxRows.map((row, i) => (
                <div key={i} className="rx-row">
                  <input className="form-input" placeholder="e.g. Paracetamol 500mg" value={row.name} onChange={e => updateRxRow(i, 'name', e.target.value)} />
                  <input className="form-input" placeholder="e.g. 1 tab" value={row.dosage} onChange={e => updateRxRow(i, 'dosage', e.target.value)} />
                  <select className="form-select" value={row.frequency} onChange={e => updateRxRow(i, 'frequency', e.target.value)}>
                    {FREQUENCY_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <input className="form-input" type="number" min={1} value={row.duration_days} onChange={e => updateRxRow(i, 'duration_days', parseInt(e.target.value) || 1)} />
                  <button className="btn btn-ghost btn-icon" onClick={() => removeRxRow(i)} disabled={rxRows.length === 1}>
                    <Trash2 size={15} color="var(--danger)" />
                  </button>
                </div>
              ))}
            </div>
            <button className="rx-add-btn" onClick={addRxRow}>
              <Plus size={15} /> Add Medication
            </button>
          </div>

          <div className="info-banner info">
            <Activity size={15} style={{ flexShrink: 0 }} />
            <span>AI will generate a patient-friendly summary and schedule medication reminders after submission.</span>
          </div>
        </Modal>
      )}
    </div>
  );
}
