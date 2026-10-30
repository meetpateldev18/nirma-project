import React, { useCallback, useEffect, useState, useMemo } from 'react';
import {
  UserPlus,
  KeyRound,
  Power,
  Users,
  UserCheck,
  Lock,
  Mail,
  Building2,
  GraduationCap,
  UploadCloud,
  FileSpreadsheet,
  Download,
  History,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import * as api from '@/lib/api-client';

const errText = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong');

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'ST';

export const UsersView: React.FC = () => {
  const [users, setUsers] = useState<api.StaffUser[]>([]);
  const [institutes, setInstitutes] = useState<api.InstituteSummary[]>([]);
  const [departments, setDepartments] = useState<api.DepartmentSummary[]>([]);
  const [auditLogs, setAuditLogs] = useState<api.AcademicAuditLog[]>([]);

  // User provision form state
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    role: 'operator',
    institute_id: '',
    department_id: '',
  });
  const [busy, setBusy] = useState(false);

  // Bulk roster ingestion state
  const [rosterFile, setRosterFile] = useState<File | null>(null);
  const [isUploadingRoster, setIsUploadingRoster] = useState(false);
  const [rosterResult, setRosterResult] = useState<api.RosterIngestionResponse | null>(null);

  const load = useCallback(() => {
    api.listUsers().then(setUsers).catch((e) => toast.error(errText(e)));
    api.listInstitutes().then(setInstitutes).catch(() => {});
    api.listAuditLogs(1, 10).then((res) => setAuditLogs(res.items)).catch(() => {});
  }, []);

  useEffect(load, [load]);

  // Load departments whenever selected institute changes
  useEffect(() => {
    if (form.institute_id) {
      api.listDepartments(Number(form.institute_id)).then((depts) => {
        setDepartments(depts);
        if (!depts.some((d) => String(d.id) === form.department_id)) {
          setForm((f) => ({ ...f, department_id: '' }));
        }
      }).catch(() => {});
    } else {
      setDepartments([]);
      setForm((f) => ({ ...f, department_id: '' }));
    }
  }, [form.institute_id, form.department_id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createUser({
        name: form.name,
        email: form.email,
        password: form.password,
        role: form.role as any,
        institute_id: form.institute_id ? Number(form.institute_id) : undefined,
        department_id: form.department_id ? Number(form.department_id) : undefined,
      });
      toast.success(`Access granted to ${form.name}`, {
        description: `Account credentials provisioned for ${form.email}. Role: ${form.role.toUpperCase()}.`,
      });
      setForm({ name: '', email: '', password: '', role: 'operator', institute_id: '', department_id: '' });
      load();
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRosterUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rosterFile) return;
    setIsUploadingRoster(true);
    setRosterResult(null);
    try {
      const result = await api.uploadStudentsRoster(rosterFile);
      setRosterResult(result);
      toast.success(`Roster Ingestion Complete`, {
        description: `Inserted ${result.inserted}, updated ${result.updated}, skipped ${result.skipped}.`,
      });
      load();
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setIsUploadingRoster(false);
    }
  };

  const toggle = async (u: api.StaffUser) => {
    try {
      await api.updateUser(u.id, { is_active: !u.is_active });
      toast.success(u.is_active ? `Suspended access for ${u.name}` : `Restored access for ${u.name}`);
      load();
    } catch (err) {
      toast.error(errText(err));
    }
  };

  const resetPassword = async (u: api.StaffUser) => {
    const password = window.prompt(`New password for ${u.name} (min 8 characters):`);
    if (!password) return;
    try {
      await api.updateUser(u.id, { password });
      toast.success(`Password updated successfully for ${u.name}`);
    } catch (err) {
      toast.error(errText(err));
    }
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  const adminCount = useMemo(() => users.filter((u) => u.role === 'admin').length, [users]);
  const operatorCount = useMemo(() => users.filter((u) => u.role !== 'admin').length, [users]);
  const activeCount = useMemo(() => users.filter((u) => u.is_active).length, [users]);

  return (
    <div className="space-y-6">
      {/* Access Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <span className="text-xs text-mute font-medium">Total Staff Accounts</span>
              <div className="text-2xl font-bold text-ink tabular-nums mt-1">{users.length}</div>
              <span className="text-[11px] text-mute font-mono">Provisioned identities</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Users className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <span className="text-xs text-mute font-medium">Faculty &amp; Operators</span>
              <div className="text-2xl font-bold text-ink tabular-nums mt-1">{operatorCount}</div>
              <span className="text-[11px] text-mute font-mono">Scoped academic access</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-live-pulse/10 text-live-pulse flex items-center justify-center">
              <UserCheck className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <span className="text-xs text-mute font-medium">System Administrators</span>
              <div className="text-2xl font-bold text-ink tabular-nums mt-1">{adminCount}</div>
              <span className="text-[11px] text-mute font-mono">University-wide authority</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-telemetry-cyan/10 text-telemetry-cyan flex items-center justify-center">
              <Lock className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Row: Provision Faculty Account & Bulk Roster Ingestion */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Provision Account Form (7 cols) */}
        <div className="lg:col-span-7">
          <Card className="h-full">
            <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-bold text-ink">Provision Staff / Faculty Account</CardTitle>
                <CardDescription className="text-xs text-body mt-0.5">
                  Issue login credentials with academic role and organizational scoping
                </CardDescription>
              </div>
              <Badge variant="mono" className="text-[10px] uppercase">
                {form.role}
              </Badge>
            </CardHeader>
            <CardContent className="p-5">
              <form onSubmit={submit} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body">Full Name</label>
                    <Input
                      required
                      minLength={2}
                      value={form.name}
                      onChange={set('name')}
                      placeholder="e.g. Dr. Rajesh Patel"
                      className="rounded-xl h-10 text-xs"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body">Institutional Email</label>
                    <Input
                      required
                      type="email"
                      value={form.email}
                      onChange={set('email')}
                      placeholder="name@nirmauni.ac.in"
                      className="rounded-xl h-10 text-xs"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body">Temporary Password</label>
                    <Input
                      required
                      minLength={8}
                      type="text"
                      value={form.password}
                      onChange={set('password')}
                      placeholder="Min 8 characters"
                      className="rounded-xl h-10 font-mono text-xs"
                    />
                  </div>
                </div>

                {/* Role & Academic Hierarchy Affiliation */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body">Clearance Role</label>
                    <Select
                      value={form.role}
                      onValueChange={(val) => setForm({ ...form, role: val })}
                    >
                      <SelectTrigger className="rounded-xl h-10 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="operator">Faculty Operator</SelectItem>
                        <SelectItem value="hod">Head of Department (HOD)</SelectItem>
                        <SelectItem value="dean">Institute Dean / Director</SelectItem>
                        <SelectItem value="program_coordinator">Program Coordinator</SelectItem>
                        <SelectItem value="class_coordinator">Class Coordinator</SelectItem>
                        <SelectItem value="faculty_mentor">Faculty Mentor</SelectItem>
                        <SelectItem value="admin">System Administrator</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body flex items-center gap-1.5">
                      <Building2 className="w-3.5 h-3.5 text-primary" />
                      Constituent Institute
                    </label>
                    <Select
                      value={form.institute_id}
                      onValueChange={(val) => setForm({ ...form, institute_id: val })}
                      disabled={form.role === 'admin'}
                    >
                      <SelectTrigger className="rounded-xl h-10 text-xs">
                        <SelectValue placeholder={form.role === 'admin' ? 'University-Wide' : 'Select Institute'} />
                      </SelectTrigger>
                      <SelectContent>
                        {institutes.map((inst) => (
                          <SelectItem key={inst.id} value={String(inst.id)}>
                            {inst.code} — {inst.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-body flex items-center gap-1.5">
                      <GraduationCap className="w-3.5 h-3.5 text-telemetry-cyan" />
                      Department
                    </label>
                    <Select
                      value={form.department_id}
                      onValueChange={(val) => setForm({ ...form, department_id: val })}
                      disabled={!form.institute_id || form.role === 'admin' || form.role === 'dean'}
                    >
                      <SelectTrigger className="rounded-xl h-10 text-xs">
                        <SelectValue
                          placeholder={
                            form.role === 'admin' || form.role === 'dean'
                              ? 'All Departments'
                              : !form.institute_id
                              ? 'Select Institute First'
                              : 'Select Department'
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {departments.map((dept) => (
                          <SelectItem key={dept.id} value={String(dept.id)}>
                            {dept.code} — {dept.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
                  <p className="text-[11px] text-mute font-mono">
                    Clearance strictly enforces ABAC data isolation on student records and call logs.
                  </p>
                  <Button
                    type="submit"
                    disabled={busy}
                    className="h-10 rounded-full px-5 text-xs font-semibold bg-primary hover:bg-primary-hover shadow-sm"
                  >
                    <UserPlus className="w-3.5 h-3.5 mr-1.5" />
                    {busy ? 'Provisioning...' : 'Provision Login'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Right: Bulk Student Roster Ingestion (5 cols) */}
        <div className="lg:col-span-5">
          <Card className="h-full flex flex-col justify-between">
            <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-bold text-ink">Bulk Roster Ingestion</CardTitle>
                <CardDescription className="text-xs text-body mt-0.5">
                  Import ERP / SIS spreadsheets (TCS iON / MyNirma)
                </CardDescription>
              </div>
              <a
                href={api.downloadRosterTemplateUrl}
                download="nirma_student_roster_template.csv"
                className="inline-flex items-center gap-1.5 text-[11px] font-mono text-primary hover:underline"
              >
                <Download className="w-3 h-3" /> Template
              </a>
            </CardHeader>
            <CardContent className="p-5 space-y-4">
              <form onSubmit={handleRosterUpload} className="space-y-3">
                <label className="flex flex-col items-center justify-center p-4 border border-dashed border-hairline-strong rounded-xl bg-canvas-elevated/40 hover:bg-canvas-elevated cursor-pointer transition-colors text-center">
                  <FileSpreadsheet className="w-8 h-8 text-primary mb-2" />
                  <span className="text-xs font-semibold text-ink">
                    {rosterFile ? rosterFile.name : 'Select or drop .csv student roster'}
                  </span>
                  <span className="text-[10px] text-mute font-mono mt-0.5">
                    Decomposes roll taxonomy, links batches &amp; divisions automatically
                  </span>
                  <input
                    type="file"
                    accept=".csv,.txt"
                    className="hidden"
                    onChange={(e) => setRosterFile(e.target.files?.[0] ?? null)}
                  />
                </label>

                <Button
                  type="submit"
                  disabled={!rosterFile || isUploadingRoster}
                  className="w-full h-10 rounded-full bg-live-pulse hover:bg-live-pulse/90 text-white text-xs font-semibold shadow-sm transition-all"
                >
                  <UploadCloud className={`w-3.5 h-3.5 mr-1.5 ${isUploadingRoster ? 'animate-spin' : ''}`} />
                  {isUploadingRoster ? 'Ingesting Student Roster...' : 'Upload & Parse Roster'}
                </Button>
              </form>

              {/* Roster Ingestion Report */}
              {rosterResult && (
                <div className="p-3.5 rounded-xl border border-hairline bg-canvas-elevated space-y-2 text-xs font-mono">
                  <div className="flex items-center justify-between font-bold text-ink border-b border-hairline/60 pb-1.5">
                    <span className="flex items-center gap-1.5 text-live-pulse">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Ingestion Report
                    </span>
                    <span>Total: {rosterResult.total_rows}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1.5 text-center text-[11px]">
                    <div className="bg-live-pulse/10 text-live-pulse p-1.5 rounded">
                      Inserted: <strong>{rosterResult.inserted}</strong>
                    </div>
                    <div className="bg-telemetry-cyan/10 text-telemetry-cyan p-1.5 rounded">
                      Updated: <strong>{rosterResult.updated}</strong>
                    </div>
                    <div className="bg-state-failed/10 text-state-failed p-1.5 rounded">
                      Skipped: <strong>{rosterResult.skipped}</strong>
                    </div>
                  </div>
                  {rosterResult.errors.length > 0 && (
                    <div className="pt-1 space-y-1">
                      <span className="text-[10px] text-state-failed font-semibold uppercase flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> Validation Errors:
                      </span>
                      <div className="max-h-24 overflow-y-auto text-[10px] text-mute space-y-0.5">
                        {rosterResult.errors.map((err, i) => (
                          <div key={i} className="truncate" title={err}>
                            • {err}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Authorized Users Table */}
      <Card>
        <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-bold text-ink">Authorized Faculty Directory</CardTitle>
            <CardDescription className="text-xs text-body mt-0.5">
              Active and suspended access privileges with academic data scoping
            </CardDescription>
          </div>
          <Badge variant="mono" className="text-[10px]">
            {activeCount} Active
          </Badge>
        </CardHeader>
        <CardContent className="p-0">
          <Table className="min-w-[720px]">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[28%]">Staff Member</TableHead>
                <TableHead className="w-[24%]">Institutional Email</TableHead>
                <TableHead className="w-[16%]">Role</TableHead>
                <TableHead className="w-[16%]">Academic Scope</TableHead>
                <TableHead className="w-[8%]">Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id} className="hover:bg-canvas-elevated/40">
                  <TableCell className="font-medium text-ink">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs shrink-0">
                        {initialsOf(u.name)}
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-ink">{u.name}</div>
                        <div className="text-[10px] text-mute font-mono">ID: #{u.id}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-body font-mono">
                    <span className="flex items-center gap-1.5">
                      <Mail className="w-3.5 h-3.5 text-mute" />
                      {u.email}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={u.role === 'admin' ? 'default' : 'secondary'}
                      className="text-[10px] font-mono capitalize"
                    >
                      {u.role.replace('_', ' ')}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {u.role === 'admin' ? (
                      <Badge variant="outline" className="text-[10px] font-mono bg-canvas-elevated text-mute border-hairline">
                        University-Wide
                      </Badge>
                    ) : u.institute_code || u.department_code ? (
                      <Badge variant="mono" className="text-[10px] font-mono bg-telemetry-cyan/10 text-telemetry-cyan border-hairline">
                        {u.institute_code || 'ITNU'} {u.department_code ? `/ ${u.department_code}` : ''}
                      </Badge>
                    ) : (
                      <span className="text-[11px] text-mute font-mono">Unassigned</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={u.is_active ? 'live' : 'destructive'}
                      className="text-[10px] font-mono flex items-center w-fit gap-1"
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-live-pulse animate-pulse' : 'bg-state-failed'}`} />
                      {u.is_active ? 'Active' : 'Suspended'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => resetPassword(u)}
                        className="h-7 text-xs rounded-full px-2.5 hover:bg-primary/10 hover:text-primary"
                      >
                        <KeyRound className="w-3 h-3 mr-1" />
                        Reset Key
                      </Button>
                      {u.role !== 'admin' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggle(u)}
                          className={`h-7 text-xs rounded-full px-2.5 ${
                            u.is_active
                              ? 'text-state-failed hover:bg-state-failed/10 hover:text-state-failed'
                              : 'text-live-pulse hover:bg-live-pulse/10 hover:text-live-pulse'
                          }`}
                        >
                          <Power className="w-3 h-3 mr-1" />
                          {u.is_active ? 'Suspend' : 'Activate'}
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Academic Compliance & Dialing Audit Trail Card */}
      {auditLogs.length > 0 && (
        <Card>
          <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-primary" />
              <div>
                <CardTitle className="text-sm font-bold text-ink">Academic Compliance Audit Trail</CardTitle>
                <CardDescription className="text-xs text-body mt-0.5">
                  Immutable event ledger tracking campaign dispatches and bulk student ingestion
                </CardDescription>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={load}
              className="h-7 text-xs rounded-full px-2 text-mute hover:text-ink"
            >
              <RefreshCw className="w-3 h-3 mr-1" /> Refresh
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            <Table className="min-w-[680px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[20%]">Action</TableHead>
                  <TableHead className="w-[25%]">Staff Initiator</TableHead>
                  <TableHead className="w-[15%]">Role</TableHead>
                  <TableHead className="w-[15%]">Scope</TableHead>
                  <TableHead className="w-[10%]">Target Size</TableHead>
                  <TableHead className="text-right">Timestamp</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditLogs.map((log) => (
                  <TableRow key={log.id} className="hover:bg-canvas-elevated/40 text-xs font-mono">
                    <TableCell className="font-semibold text-ink">
                      <Badge variant="outline" className="text-[10px] capitalize">
                        {log.action.replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-body">{log.staff_email}</TableCell>
                    <TableCell className="text-mute capitalize">{log.staff_role}</TableCell>
                    <TableCell className="text-telemetry-cyan font-semibold">
                      {log.institute_code || 'ITNU'} {log.department_code ? `/ ${log.department_code}` : ''}
                    </TableCell>
                    <TableCell className="tabular-nums font-bold text-ink">{log.target_count} students</TableCell>
                    <TableCell className="text-right text-mute tabular-nums">
                      {new Date(log.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default UsersView;
