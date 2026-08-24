import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search, Calendar, Ticket, Activity, FileText,
  RefreshCw, Clock, CheckCircle, AlertCircle, ChevronRight
} from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import Modal from '../components/Modal';

const TIERS = [
  { id: 'regular', label: 'Regular', desc: 'Standard appointment (FCFS)', color: 'regular' },
  { id: 'priority', label: 'Priority', desc: 'Priority access for seniors & urgent cases', color: 'priority' },
];

const SESSIONS = ['morning', 'evening'];
const TODAY = new Date().toISOString().split('T')[0];

export default function PatientPortal({ onToast }) {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('book');

  // --- Book tab ---
  const [doctors, setDoctors] = useState([]);
  const [loadingDoctors, setLoadingDoctors] = useState(false);
  const [search, setSearch] = useState('');
  const [aiSuggestPrompt, setAiSuggestPrompt] = useState('');
  const [aiSuggesting, setAiSuggesting] = useState(false);
  const [aiRecommendation, setAiRecommendation] = useState(null);
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [bookingForm, setBookingForm] = useState({ date: TODAY, session: 'morning', tier: 'regular' });
  const [booking, setBooking] = useState(false);
  const [bookedEntry, setBookedEntry] = useState(() => {
    try { return JSON.parse(localStorage.getItem('hq_my_token') || 'null'); } catch { return null; }
  });
  const [symptomText, setSymptomText] = useState('');
  const [symptomSending, setSymptomSending] = useState(false);
  const [symptomDone, setSymptomDone] = useState(false);

  // --- Live Tracker tab ---
  const [queueStatus, setQueueStatus] = useState(null);
  const [trackLoading, setTrackLoading] = useState(false);
  const trackInterval = useRef(null);

  // --- Records tab ---
  const [records, setRecords] = useState(null);
  const [loadingRecords, setLoadingRecords] = useState(false);

  // Fetch doctors on mount / search change
  useEffect(() => {
    setLoadingDoctors(true);
    api.doctors.list(search ? { specialisation: search } : {})
      .then(setDoctors)
      .catch(() => setDoctors([]))
      .finally(() => setLoadingDoctors(false));
  }, [search]);

  // Poll queue status when on tracker tab and have a booking
  useEffect(() => {
    if (activeTab === 'track' && bookedEntry?.id) {
      const poll = () => {
        setTrackLoading(true);
        api.queue.status(bookedEntry.id)
          .then(setQueueStatus)
          .catch(() => {})
          .finally(() => setTrackLoading(false));
      };
      poll();
      trackInterval.current = setInterval(poll, 20000);
    }
    return () => clearInterval(trackInterval.current);
  }, [activeTab, bookedEntry?.id]);

  // Fetch post-visit records
  useEffect(() => {
    if (activeTab === 'records' && bookedEntry?.id) {
      setLoadingRecords(true);
      api.clinical.getNotes(bookedEntry.id)
        .then(setRecords)
        .catch(() => setRecords(null))
        .finally(() => setLoadingRecords(false));
    }
  }, [activeTab, bookedEntry?.id]);

  const handleBook = async () => {
    if (!selectedDoctor) { onToast('warning', 'Select a doctor', 'Please choose a doctor first.'); return; }
    setBooking(true);
    try {
      const entry = await api.queue.book({
        doctor_id: selectedDoctor.id,
        patient_id: user.id,
        appointment_date: bookingForm.date,
        session: bookingForm.session,
        tier: bookingForm.tier,
        booking_mode: 'advance',
      });
      localStorage.setItem('hq_my_token', JSON.stringify(entry));
      setBookedEntry(entry);
      onToast('success', 'Token booked!', `Your token #${entry.token_number} is confirmed.`);
      setActiveTab('track');
    } catch (err) {
      onToast('error', 'Booking failed', err.message);
    } finally {
      setBooking(false);
    }
  };

  const handleSymptomSubmit = async () => {
    if (!symptomText.trim()) { onToast('warning', 'Enter symptoms', 'Please describe your symptoms.'); return; }
    setSymptomSending(true);
    try {
      await api.clinical.submitSymptoms(bookedEntry.id, symptomText);
      setSymptomDone(true);
      onToast('success', 'Symptoms submitted', 'Our AI will prepare a triage brief for your doctor.');
    } catch (err) {
      onToast('error', 'Submission failed', err.message);
    } finally {
      setSymptomSending(false);
    }
  };

  const handleRefreshStatus = () => {
    if (!bookedEntry?.id) return;
    setTrackLoading(true);
    api.queue.status(bookedEntry.id)
      .then(setQueueStatus)
      .catch(() => {})
      .finally(() => setTrackLoading(false));
  };

  const handleAiSuggest = async () => {
    if (!aiSuggestPrompt.trim()) {
      onToast('warning', 'Describe symptoms', 'Please enter your symptoms or health concern.');
      return;
    }
    setAiSuggesting(true);
    try {
      const res = await api.doctors.suggestBySymptoms(aiSuggestPrompt);
      setAiRecommendation(res);
      setDoctors(res.doctors || []);
      onToast('success', `Recommended: ${res.recommended_specialisation}`, res.reason);
    } catch (err) {
      onToast('error', 'AI suggestion failed', err.message);
    } finally {
      setAiSuggesting(false);
    }
  };

  const filteredDoctors = doctors.filter(d =>
    !search || d.specialisation?.toLowerCase().includes(search.toLowerCase())
  );

  const tabs = [
    { id: 'book', label: 'Book Appointment', icon: <Calendar size={15} /> },
    { id: 'track', label: 'Live Queue', icon: <Activity size={15} /> },
    { id: 'symptoms', label: 'Pre-Visit Intake', icon: <FileText size={15} /> },
    { id: 'records', label: 'Post-Visit Records', icon: <CheckCircle size={15} /> },
  ];

  return (
    <div>
      <div className="section-header">
        <div>
          <h2 className="section-title">Patient Portal</h2>
          <p className="section-subtitle">Book appointments, track your queue position, and view visit records</p>
        </div>
      </div>

      <div className="page-tabs">
        {tabs.map(t => (
          <button key={t.id} className={`page-tab ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ===== BOOK TAB ===== */}
      {activeTab === 'book' && (
        <div className="grid-main-side">
          {/* Left: Doctor search */}
          <div className="flex flex-col gap-4">
            {/* AI Auto-Suggest by Symptoms */}
            <div className="card card-pad" style={{ background: 'var(--card-bg-glass, var(--bg-card))', border: '1px solid var(--primary-border, var(--border-color))' }}>
              <div className="flex items-center gap-2 mb-2">
                <Activity size={16} color="var(--primary)" />
                <span className="font-600 text-sm">AI Doctor Matcher (By Symptoms / Diagnosis)</span>
              </div>
              <div className="flex gap-2">
                <input
                  className="form-input"
                  style={{ margin: 0 }}
                  placeholder="e.g. chest heaviness, skin rash with itching, migraine..."
                  value={aiSuggestPrompt}
                  onChange={e => setAiSuggestPrompt(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleAiSuggest()}
                />
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handleAiSuggest}
                  disabled={aiSuggesting}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  {aiSuggesting ? <><span className="spinner spinner-sm" /> Matching…</> : 'AI Match'}
                </button>
              </div>
              {aiRecommendation && (
                <div className="mt-3 p-2 rounded text-xs" style={{ background: 'rgba(59, 130, 246, 0.1)', borderLeft: '3px solid #3b82f6' }}>
                  <strong>Recommended: {aiRecommendation.recommended_specialisation}</strong> — {aiRecommendation.reason}
                </div>
              )}
            </div>

            <div className="card card-pad">
              <div className="flex items-center gap-3 mb-4">
                <Search size={16} color="var(--text-muted)" />
                <input
                  className="form-input"
                  placeholder="Or filter by doctor specialisation directly…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={{ margin: 0 }}
                />
              </div>
              {loadingDoctors ? (
                <div className="loading-overlay"><span className="spinner" /> Loading doctors…</div>
              ) : filteredDoctors.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon"><Search size={32} /></div>
                  <h3>No doctors found</h3>
                  <p>Try a different search or click AI Match</p>
                </div>
              ) : (
                <div className="grid-2">
                  {filteredDoctors.map(doc => (
                    <div
                      key={doc.id}
                      className={`doctor-card ${selectedDoctor?.id === doc.id ? 'selected' : ''}`}
                      onClick={() => setSelectedDoctor(doc)}
                    >
                      <div className="doctor-avatar">{(doc.specialisation?.[0] || 'D').toUpperCase()}</div>
                      <div className="doctor-name">Dr. #{doc.id}</div>
                      <div className="doctor-spec">{doc.specialisation}</div>
                      <div className="doctor-meta">
                        <span className="badge badge-neutral">{doc.booking_mode}</span>
                        {doc.experience_years && <span className="text-xs text-muted">{doc.experience_years} yrs exp</span>}
                      </div>
                      {doc.bio && <p className="text-xs text-secondary mt-2">{doc.bio}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right: Booking form */}
          <div className="flex flex-col gap-4">
            <div className="card card-pad">
              <h3 className="font-600 mb-4">Appointment Details</h3>

              <div className="flex flex-col gap-4">
                <div className="form-group">
                  <label className="form-label">Date</label>
                  <input
                    id="book-date"
                    className="form-input"
                    type="date"
                    min={TODAY}
                    value={bookingForm.date}
                    onChange={e => setBookingForm(p => ({ ...p, date: e.target.value }))}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Session</label>
                  <select
                    id="book-session"
                    className="form-select"
                    value={bookingForm.session}
                    onChange={e => setBookingForm(p => ({ ...p, session: e.target.value }))}
                  >
                    {SESSIONS.map(s => (
                      <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Appointment Tier</label>
                  <div className="tier-selector">
                    {TIERS.map(t => (
                      <button
                        key={t.id}
                        type="button"
                        className={`tier-option ${bookingForm.tier === t.id ? `selected ${t.color}` : ''}`}
                        onClick={() => setBookingForm(p => ({ ...p, tier: t.id }))}
                      >
                        <div className={`tier-option-label`} style={bookingForm.tier === t.id ? { color: `var(--tier-${t.color})` } : {}}>{t.label}</div>
                        <div className="tier-option-desc">{t.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {selectedDoctor && (
                  <div className="info-banner success">
                    <CheckCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                    <span>Dr. #{selectedDoctor.id} — {selectedDoctor.specialisation} selected</span>
                  </div>
                )}

                <button
                  id="book-submit"
                  className="btn btn-primary btn-lg w-full"
                  onClick={handleBook}
                  disabled={booking || !selectedDoctor}
                >
                  {booking ? <><span className="spinner spinner-sm" /> Booking…</> : <><Ticket size={16} /> Confirm Booking</>}
                </button>
              </div>
            </div>

            {bookedEntry && (
              <div className="info-banner success">
                <CheckCircle size={16} style={{ flexShrink: 0 }} />
                <div>
                  <strong>Active Token #{bookedEntry.token_number}</strong>
                  <div className="text-xs mt-1">Go to Live Queue tab to track your position.</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== LIVE TRACK TAB ===== */}
      {activeTab === 'track' && (
        <div className="flex flex-col gap-4" style={{ maxWidth: 560, margin: '0 auto' }}>
          {!bookedEntry ? (
            <div className="empty-state">
              <div className="empty-state-icon"><Ticket size={48} /></div>
              <h3>No active booking</h3>
              <p>Book an appointment first to track your queue position.</p>
              <button className="btn btn-primary mt-4" onClick={() => setActiveTab('book')}>Book Now</button>
            </div>
          ) : (
            <>
              <div className="live-tracker">
                <div className="live-token-label">Your Token Number</div>
                <div className="live-token-number">#{bookedEntry.token_number}</div>
                {queueStatus ? (
                  <>
                    <div className="live-serving">
                      Position in queue: <strong>{queueStatus.display_position ?? '—'}</strong>
                    </div>
                    <div className="live-eta">
                      <Clock size={13} style={{ display: 'inline', marginRight: 4 }} />
                      Status: <strong>{queueStatus.status ?? 'waiting'}</strong>
                      {queueStatus.estimated_wait_minutes != null && (
                        <> · Est. wait: <strong>~{queueStatus.estimated_wait_minutes} min</strong></>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="live-eta">Loading queue status…</div>
                )}
                <div className="live-ping">
                  <span className="pulse-dot" />
                  Auto-refreshes every 20 seconds
                </div>
              </div>

              <button
                id="refresh-status"
                className="btn btn-secondary w-full"
                onClick={handleRefreshStatus}
                disabled={trackLoading}
              >
                {trackLoading ? <><span className="spinner spinner-sm" /> Refreshing…</> : <><RefreshCw size={15} /> Refresh Now</>}
              </button>

              <div className="card card-pad">
                <div className="text-sm font-600 mb-3">Booking Details</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 'var(--text-sm)' }}>
                  <div className="flex justify-between"><span className="text-muted">Doctor</span><span>Dr. #{bookedEntry.doctor_id}</span></div>
                  <div className="divider" />
                  <div className="flex justify-between"><span className="text-muted">Date</span><span>{bookedEntry.appointment_date}</span></div>
                  <div className="divider" />
                  <div className="flex justify-between"><span className="text-muted">Session</span><span>{bookedEntry.session}</span></div>
                  <div className="divider" />
                  <div className="flex justify-between"><span className="text-muted">Tier</span><span className={`badge badge-${bookedEntry.tier}`}>{bookedEntry.tier}</span></div>
                </div>
              </div>

              <button
                className="btn btn-ghost btn-sm"
                style={{ color: 'var(--danger)' }}
                onClick={() => { localStorage.removeItem('hq_my_token'); setBookedEntry(null); setQueueStatus(null); }}
              >
                Clear booking record
              </button>
            </>
          )}
        </div>
      )}

      {/* ===== SYMPTOM INTAKE TAB ===== */}
      {activeTab === 'symptoms' && (
        <div style={{ maxWidth: 600, margin: '0 auto' }}>
          {!bookedEntry ? (
            <div className="empty-state">
              <div className="empty-state-icon"><FileText size={48} /></div>
              <h3>No active booking</h3>
              <p>You need to book an appointment before submitting symptoms.</p>
              <button className="btn btn-primary mt-4" onClick={() => setActiveTab('book')}>Book Now</button>
            </div>
          ) : symptomDone ? (
            <div className="card card-pad" style={{ textAlign: 'center', padding: 48 }}>
              <CheckCircle size={48} color="var(--success)" style={{ margin: '0 auto 16px' }} />
              <h3 className="font-700" style={{ fontSize: 'var(--text-xl)' }}>Symptoms Submitted</h3>
              <p className="text-secondary mt-2">Our AI has processed your symptoms and prepared a clinical triage brief for your doctor.</p>
              <button className="btn btn-secondary mt-4" onClick={() => setActiveTab('track')}>View Queue Status</button>
            </div>
          ) : (
            <div className="card card-pad flex flex-col gap-4">
              <div>
                <h3 className="font-600" style={{ marginBottom: 6 }}>Pre-Visit Symptom Intake</h3>
                <p className="text-sm text-secondary">Describe your symptoms in detail. Our AI will analyze them and prepare a triage brief for your doctor before your consultation.</p>
              </div>

              <div className="info-banner info">
                <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>This intake helps your doctor understand your condition better. Be as specific as possible.</span>
              </div>

              <div className="form-group">
                <label className="form-label">Describe your symptoms <span className="text-muted">({symptomText.length}/500)</span></label>
                <textarea
                  id="symptom-textarea"
                  className="form-textarea"
                  maxLength={500}
                  style={{ minHeight: 160 }}
                  value={symptomText}
                  onChange={e => setSymptomText(e.target.value)}
                  placeholder="e.g. I've had a persistent headache for 3 days, mild fever around 99°F, and slight nausea in the mornings…"
                />
              </div>

              <button
                id="symptom-submit"
                className="btn btn-primary btn-lg"
                onClick={handleSymptomSubmit}
                disabled={symptomSending || !symptomText.trim()}
              >
                {symptomSending ? <><span className="spinner spinner-sm" /> Submitting…</> : 'Submit Symptoms for AI Triage'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ===== RECORDS TAB ===== */}
      {activeTab === 'records' && (
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          {!bookedEntry ? (
            <div className="empty-state">
              <div className="empty-state-icon"><FileText size={48} /></div>
              <h3>No active booking</h3>
              <p>Records will appear after your consultation.</p>
            </div>
          ) : loadingRecords ? (
            <div className="loading-overlay"><span className="spinner" /> Loading records…</div>
          ) : !records ? (
            <div className="empty-state">
              <div className="empty-state-icon"><Clock size={48} /></div>
              <h3>No records yet</h3>
              <p>Your doctor hasn't submitted post-visit notes yet. Check back after your consultation.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="card card-pad">
                <h3 className="font-600 mb-3">Doctor's Clinical Notes</h3>
                <p className="text-sm" style={{ lineHeight: 1.8 }}>{records.raw_notes || 'No raw notes available.'}</p>
              </div>

              {records.ai_summary && (
                <div className="card card-pad">
                  <h3 className="font-600 mb-3">AI Patient Summary</h3>
                  <p className="text-sm" style={{ lineHeight: 1.8, color: 'var(--text-secondary)' }}>{records.ai_summary}</p>
                </div>
              )}

              {records.medications?.length > 0 && (
                <div className="card card-pad">
                  <h3 className="font-600 mb-3">Prescribed Medications</h3>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Medication</th>
                          <th>Dosage</th>
                          <th>Frequency</th>
                          <th>Duration</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.medications.map((m, i) => (
                          <tr key={i}>
                            <td className="font-600">{m.name}</td>
                            <td>{m.dosage}</td>
                            <td>{m.frequency}</td>
                            <td>{m.duration_days} days</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
