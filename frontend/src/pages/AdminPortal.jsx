import { useState, useEffect } from 'react';
import {
  Users, Calendar, Activity, AlertTriangle, Plus, Trash2,
  Stethoscope, Clock, BarChart2, CheckCircle, Settings
} from 'lucide-react';
import { api } from '../services/api';
import Modal from '../components/Modal';

const TODAY = new Date().toISOString().split('T')[0];
const SPECIALISATIONS = [
  'General Practice', 'Cardiology', 'Dermatology', 'Endocrinology',
  'Gastroenterology', 'Neurology', 'Oncology', 'Ophthalmology',
  'Orthopedics', 'Pediatrics', 'Psychiatry', 'Pulmonology',
  'Radiology', 'Urology', 'ENT', 'Obstetrics & Gynecology'
];

function StatCard({ icon, label, value, color }) {
  return (
    <div className="stat-card">
      <div className="stat-card-icon" style={{ color }}>{icon}</div>
      <div className="stat-card-label">{label}</div>
      <div className="stat-card-value">{value ?? '—'}</div>
    </div>
  );
}

export default function AdminPortal({ onToast }) {
  const [activeTab, setActiveTab] = useState('dashboard');

  // Dashboard stats
  const [stats, setStats] = useState(null);
  const [loadingStats, setLoadingStats] = useState(false);

  // Doctor management
  const [doctors, setDoctors] = useState([]);
  const [loadingDoctors, setLoadingDoctors] = useState(false);
  const [createDoctorModal, setCreateDoctorModal] = useState(false);
  const [createDoctorForm, setCreateDoctorForm] = useState({
    user_id: '', specialisation: 'General Practice', bio: '',
    experience_years: '', slot_duration_minutes: 15, booking_mode: 'hybrid',
    anchor_slot_pct: 25, priority_slot_pct: 25, emergency_slot_pct: 10,
  });
  const [creatingDoctor, setCreatingDoctor] = useState(false);

  // Availability modal
  const [availModal, setAvailModal] = useState(null); // { doctorId }
  const [availForm, setAvailForm] = useState({ day_of_week: 1, session: 'morning', start_time: '09:00', end_time: '13:00', is_working_day: true });
  const [savingAvail, setSavingAvail] = useState(false);

  // Leave modal
  const [leaveModal, setLeaveModal] = useState(null); // { doctorId }
  const [leaveForm, setLeaveForm] = useState({ start_date: TODAY, end_date: TODAY, reason: '' });
  const [savingLeave, setSavingLeave] = useState(false);
  const [leaveResult, setLeaveResult] = useState(null);

  useEffect(() => {
    if (activeTab === 'dashboard') {
      setLoadingStats(true);
      api.admin.dashboard()
        .then(setStats)
        .catch(() => setStats(null))
        .finally(() => setLoadingStats(false));
    }
    if (activeTab === 'doctors') {
      setLoadingDoctors(true);
      api.doctors.list()
        .then(setDoctors)
        .catch(() => setDoctors([]))
        .finally(() => setLoadingDoctors(false));
    }
  }, [activeTab]);

  const handleCreateDoctor = async () => {
    if (!createDoctorForm.user_id) { onToast('warning', 'User ID required', 'Enter the user ID for this doctor.'); return; }
    setCreatingDoctor(true);
    try {
      await api.doctors.create({
        ...createDoctorForm,
        user_id: parseInt(createDoctorForm.user_id),
        experience_years: parseInt(createDoctorForm.experience_years) || null,
        slot_duration_minutes: parseInt(createDoctorForm.slot_duration_minutes),
        anchor_slot_pct: parseFloat(createDoctorForm.anchor_slot_pct),
        priority_slot_pct: parseFloat(createDoctorForm.priority_slot_pct),
        emergency_slot_pct: parseFloat(createDoctorForm.emergency_slot_pct),
      });
      onToast('success', 'Doctor created', 'Doctor profile successfully set up.');
      setCreateDoctorModal(false);
      setCreateDoctorForm({ user_id: '', specialisation: 'General Practice', bio: '', experience_years: '', slot_duration_minutes: 15, booking_mode: 'hybrid', anchor_slot_pct: 25, priority_slot_pct: 25, emergency_slot_pct: 10 });
      setLoadingDoctors(true);
      api.doctors.list().then(setDoctors).finally(() => setLoadingDoctors(false));
    } catch (err) {
      onToast('error', 'Creation failed', err.message);
    } finally {
      setCreatingDoctor(false);
    }
  };

  const handleSaveAvailability = async () => {
    setSavingAvail(true);
    try {
      await api.doctors.setAvailability(availModal.doctorId, availForm);
      onToast('success', 'Availability saved', 'Working hours updated successfully.');
      setAvailModal(null);
    } catch (err) {
      onToast('error', 'Failed to save', err.message);
    } finally {
      setSavingAvail(false);
    }
  };

  const handleAddLeave = async () => {
    setSavingLeave(true);
    setLeaveResult(null);
    try {
      const result = await api.doctors.addLeave(leaveModal.doctorId, leaveForm);
      setLeaveResult(result);
      onToast('success', 'Leave created', `${result.cancelled_appointments} appointments auto-cancelled.`);
      setLoadingDoctors(true);
      api.doctors.list().then(setDoctors).finally(() => setLoadingDoctors(false));
    } catch (err) {
      onToast('error', 'Failed to add leave', err.message);
    } finally {
      setSavingLeave(false);
    }
  };

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: <BarChart2 size={15} /> },
    { id: 'doctors', label: 'Doctor Management', icon: <Stethoscope size={15} /> },
  ];

  return (
    <div>
      <div className="section-header">
        <div>
          <h2 className="section-title">Admin Control Center</h2>
          <p className="section-subtitle">System overview, doctor management, leave control, and capacity configuration</p>
        </div>
        {activeTab === 'doctors' && (
          <button id="create-doctor-btn" className="btn btn-primary" onClick={() => setCreateDoctorModal(true)}>
            <Plus size={16} /> Add Doctor
          </button>
        )}
      </div>

      <div className="page-tabs">
        {tabs.map(t => (
          <button key={t.id} className={`page-tab ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ===== DASHBOARD TAB ===== */}
      {activeTab === 'dashboard' && (
        <div className="flex flex-col gap-6">
          {loadingStats ? (
            <div className="loading-overlay"><span className="spinner" /> Loading dashboard…</div>
          ) : !stats ? (
            <div className="info-banner warning">
              <AlertTriangle size={16} style={{ flexShrink: 0 }} />
              <span>Dashboard stats unavailable. Backend may not be connected. Start the server with <code>uv run uvicorn src.main:app --reload</code>.</span>
            </div>
          ) : (
            <div className="grid-4">
              <StatCard icon={<Stethoscope size={22} />} label="Active Doctors" value={stats.active_doctors} color="var(--primary)" />
              <StatCard icon={<Calendar size={22} />} label="Bookings Today" value={stats.bookings_today} color="var(--success)" />
              <StatCard icon={<AlertTriangle size={22} />} label="Urgent Triages" value={stats.urgent_triages} color="var(--tier-emergency)" />
              <StatCard icon={<Clock size={22} />} label="Avg Delay (min)" value={stats.avg_delay_minutes != null ? `${stats.avg_delay_minutes} min` : '0 min'} color="var(--warning)" />
            </div>
          )}

          <div className="card card-pad">
            <h3 className="font-600 mb-4">System Status</h3>
            <div className="flex flex-col gap-3">
              {[
                { label: 'API Backend', ok: !!stats },
                { label: 'AI Triage Engine', ok: !!stats },
                { label: 'Queue Engine', ok: !!stats },
                { label: 'Notification Service', ok: false },
                { label: 'Google Calendar Sync', ok: false },
              ].map(({ label, ok }) => (
                <div key={label} className="flex items-center justify-between" style={{ padding: '10px 14px', background: 'var(--bg-sidebar)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                  <span className="text-sm font-600">{label}</span>
                  <span className={`badge ${ok ? 'badge-success' : 'badge-danger'}`}>
                    <span className={`status-dot ${ok ? 'green' : 'red'}`} />
                    {ok ? 'Operational' : 'Offline'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ===== DOCTORS TAB ===== */}
      {activeTab === 'doctors' && (
        <div>
          {loadingDoctors ? (
            <div className="loading-overlay"><span className="spinner" /> Loading doctors…</div>
          ) : doctors.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon"><Stethoscope size={48} /></div>
              <h3>No doctors registered</h3>
              <p>Add your first doctor profile to get started.</p>
              <button className="btn btn-primary mt-4" onClick={() => setCreateDoctorModal(true)}>
                <Plus size={15} /> Add Doctor
              </button>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Specialisation</th>
                    <th>Booking Mode</th>
                    <th>Slot (min)</th>
                    <th>Priority %</th>
                    <th>Emergency %</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {doctors.map(doc => (
                    <tr key={doc.id}>
                      <td className="font-700">#{doc.id}</td>
                      <td>{doc.specialisation}</td>
                      <td><span className="badge badge-neutral">{doc.booking_mode}</span></td>
                      <td>{doc.slot_duration_minutes}</td>
                      <td>{doc.priority_slot_pct}%</td>
                      <td>{doc.emergency_slot_pct}%</td>
                      <td>
                        <span className={`badge ${doc.is_available ? 'badge-success' : 'badge-danger'}`}>
                          <span className={`status-dot ${doc.is_available ? 'green' : 'red'}`} />
                          {doc.is_available ? 'Available' : 'Unavailable'}
                        </span>
                      </td>
                      <td>
                        <div className="flex gap-2">
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => { setAvailModal({ doctorId: doc.id }); setAvailForm({ day_of_week: 1, session: 'morning', start_time: '09:00', end_time: '13:00', is_working_day: true }); }}
                          >
                            <Calendar size={13} /> Hours
                          </button>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => { setLeaveModal({ doctorId: doc.id }); setLeaveResult(null); setLeaveForm({ start_date: TODAY, end_date: TODAY, reason: '' }); }}
                          >
                            <Clock size={13} /> Leave
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ===== CREATE DOCTOR MODAL ===== */}
      {createDoctorModal && (
        <Modal
          title="Add Doctor Profile"
          subtitle="Create a new doctor profile for an existing doctor-role user"
          onClose={() => setCreateDoctorModal(false)}
          size="modal-lg"
          footer={
            <>
              <button className="btn btn-secondary" onClick={() => setCreateDoctorModal(false)}>Cancel</button>
              <button id="create-doctor-submit" className="btn btn-primary" onClick={handleCreateDoctor} disabled={creatingDoctor}>
                {creatingDoctor ? <><span className="spinner spinner-sm" /> Creating…</> : 'Create Doctor Profile'}
              </button>
            </>
          }
        >
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">User ID <span style={{ color: 'var(--danger)' }}>*</span></label>
              <input id="doctor-user-id" className="form-input" type="number" placeholder="Existing user ID" value={createDoctorForm.user_id} onChange={e => setCreateDoctorForm(p => ({ ...p, user_id: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Experience (years)</label>
              <input className="form-input" type="number" placeholder="e.g. 10" value={createDoctorForm.experience_years} onChange={e => setCreateDoctorForm(p => ({ ...p, experience_years: e.target.value }))} />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Specialisation</label>
            <select className="form-select" value={createDoctorForm.specialisation} onChange={e => setCreateDoctorForm(p => ({ ...p, specialisation: e.target.value }))}>
              {SPECIALISATIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Bio (optional)</label>
            <textarea className="form-textarea" style={{ minHeight: 70 }} value={createDoctorForm.bio} onChange={e => setCreateDoctorForm(p => ({ ...p, bio: e.target.value }))} placeholder="Brief professional description…" />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Slot Duration (minutes)</label>
              <input className="form-input" type="number" min={5} value={createDoctorForm.slot_duration_minutes} onChange={e => setCreateDoctorForm(p => ({ ...p, slot_duration_minutes: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Booking Mode</label>
              <select className="form-select" value={createDoctorForm.booking_mode} onChange={e => setCreateDoctorForm(p => ({ ...p, booking_mode: e.target.value }))}>
                <option value="hybrid">Hybrid</option>
                <option value="walk_in">Walk-in Only</option>
                <option value="advance_only">Advance Only</option>
              </select>
            </div>
          </div>

          <div className="form-row-3">
            <div className="form-group">
              <label className="form-label">Anchor Slots %</label>
              <input className="form-input" type="number" min={0} max={100} value={createDoctorForm.anchor_slot_pct} onChange={e => setCreateDoctorForm(p => ({ ...p, anchor_slot_pct: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Priority Slots %</label>
              <input className="form-input" type="number" min={0} max={100} value={createDoctorForm.priority_slot_pct} onChange={e => setCreateDoctorForm(p => ({ ...p, priority_slot_pct: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Emergency Slots %</label>
              <input className="form-input" type="number" min={0} max={100} value={createDoctorForm.emergency_slot_pct} onChange={e => setCreateDoctorForm(p => ({ ...p, emergency_slot_pct: e.target.value }))} />
            </div>
          </div>
        </Modal>
      )}

      {/* ===== AVAILABILITY MODAL ===== */}
      {availModal && (
        <Modal
          title="Set Working Hours"
          subtitle={`Doctor #${availModal.doctorId}`}
          onClose={() => setAvailModal(null)}
          footer={
            <>
              <button className="btn btn-secondary" onClick={() => setAvailModal(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSaveAvailability} disabled={savingAvail}>
                {savingAvail ? <><span className="spinner spinner-sm" /> Saving…</> : 'Save Hours'}
              </button>
            </>
          }
        >
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Day of Week</label>
              <select className="form-select" value={availForm.day_of_week} onChange={e => setAvailForm(p => ({ ...p, day_of_week: parseInt(e.target.value) }))}>
                {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((d,i) => (
                  <option key={i} value={i}>{d}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Session</label>
              <select className="form-select" value={availForm.session} onChange={e => setAvailForm(p => ({ ...p, session: e.target.value }))}>
                <option value="morning">Morning</option>
                <option value="evening">Evening</option>
                <option value="full_day">Full Day</option>
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Start Time</label>
              <input className="form-input" type="time" value={availForm.start_time} onChange={e => setAvailForm(p => ({ ...p, start_time: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">End Time</label>
              <input className="form-input" type="time" value={availForm.end_time} onChange={e => setAvailForm(p => ({ ...p, end_time: e.target.value }))} />
            </div>
          </div>
          <div className="settings-item" style={{ cursor: 'default' }}>
            <div className="settings-item-left">
              <div className="settings-item-info">
                <h4>Working Day</h4>
                <p>Toggle off to mark as non-working day</p>
              </div>
            </div>
            <button className={`toggle ${availForm.is_working_day ? 'on' : ''}`} onClick={() => setAvailForm(p => ({ ...p, is_working_day: !p.is_working_day }))} />
          </div>
        </Modal>
      )}

      {/* ===== LEAVE MODAL ===== */}
      {leaveModal && (
        <Modal
          title="Add Doctor Leave"
          subtitle={`Doctor #${leaveModal.doctorId} — All conflicting appointments will be auto-cancelled`}
          onClose={() => setLeaveModal(null)}
          footer={
            leaveResult ? (
              <button className="btn btn-secondary" onClick={() => setLeaveModal(null)}>Close</button>
            ) : (
              <>
                <button className="btn btn-secondary" onClick={() => setLeaveModal(null)}>Cancel</button>
                <button className="btn btn-danger" onClick={handleAddLeave} disabled={savingLeave}>
                  {savingLeave ? <><span className="spinner spinner-sm" /> Processing…</> : 'Confirm Leave & Auto-Cancel'}
                </button>
              </>
            )
          }
        >
          {leaveResult ? (
            <div className="flex flex-col gap-3">
              <div className="info-banner success">
                <CheckCircle size={16} style={{ flexShrink: 0 }} />
                <div>
                  <strong>Leave created successfully</strong>
                  <div className="text-xs mt-1">Leave ID #{leaveResult.leave_id}</div>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div className="stat-card">
                  <div className="stat-card-label">Appointments Cancelled</div>
                  <div className="stat-card-value">{leaveResult.cancelled_appointments}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-card-label">Notifications Queued</div>
                  <div className="stat-card-value">{leaveResult.notifications_queued}</div>
                </div>
              </div>
              <div className="info-banner info">
                <AlertTriangle size={15} style={{ flexShrink: 0 }} />
                <span>WhatsApp and email notifications have been queued for all affected patients.</span>
              </div>
            </div>
          ) : (
            <>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Start Date</label>
                  <input className="form-input" type="date" value={leaveForm.start_date} onChange={e => setLeaveForm(p => ({ ...p, start_date: e.target.value }))} />
                </div>
                <div className="form-group">
                  <label className="form-label">End Date</label>
                  <input className="form-input" type="date" value={leaveForm.end_date} min={leaveForm.start_date} onChange={e => setLeaveForm(p => ({ ...p, end_date: e.target.value }))} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Reason (optional)</label>
                <input className="form-input" value={leaveForm.reason} onChange={e => setLeaveForm(p => ({ ...p, reason: e.target.value }))} placeholder="e.g. Medical conference, personal leave…" />
              </div>
              <div className="info-banner warning">
                <AlertTriangle size={15} style={{ flexShrink: 0 }} />
                <span>All appointments in this date range will be automatically cancelled and patients notified via WhatsApp &amp; Email.</span>
              </div>
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
