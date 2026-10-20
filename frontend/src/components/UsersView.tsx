import React, { useCallback, useEffect, useState, useMemo } from 'react';
import { UserPlus, KeyRound, Power, ShieldCheck, Users, UserCheck, Lock, Mail } from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import * as api from '@/lib/api-client';

const errText = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong');

const initialsOf = (name: string) =>
  name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'ST';

export const UsersView: React.FC = () => {
  const [users, setUsers] = useState<api.StaffUser[]>([]);
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.listUsers().then(setUsers).catch((e) => toast.error(errText(e)));
  }, []);

  useEffect(load, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createUser({ ...form, role: 'operator' });
      toast.success(`Access granted to ${form.name}`, {
        description: `Account credentials sent for ${form.email}. Role: Faculty Operator.`,
      });
      setForm({ name: '', email: '', password: '' });
      load();
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setBusy(false);
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
  const operatorCount = useMemo(() => users.filter((u) => u.role === 'operator').length, [users]);
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
              <span className="text-xs text-mute font-medium">Faculty Operators</span>
              <div className="text-2xl font-bold text-ink tabular-nums mt-1">{operatorCount}</div>
              <span className="text-[11px] text-mute font-mono">Scoped campaign access</span>
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
              <span className="text-[11px] text-mute font-mono">Full system authority</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-telemetry-cyan/10 text-telemetry-cyan flex items-center justify-center">
              <Lock className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Provision Access Card */}
      <Card>
        <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-bold text-ink">Provision Faculty Account</CardTitle>
            <CardDescription className="text-xs text-body mt-0.5">
              Issue operator credentials with email authentication
            </CardDescription>
          </div>
          <Badge variant="mono" className="text-[10px]">
            Role: Operator
          </Badge>
        </CardHeader>
        <CardContent className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-body">Full Name</label>
                <Input
                  required
                  minLength={2}
                  value={form.name}
                  onChange={set('name')}
                  placeholder="e.g. Dr. Rajesh Patel"
                  className="rounded-xl h-10"
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
                  className="rounded-xl h-10"
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

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
              <p className="text-[11px] text-mute font-mono">
                Faculty operators can only place calls and inspect transcripts under their own login.
              </p>
              <Button
                type="submit"
                disabled={busy}
                className="h-10 rounded-full px-5 text-xs font-semibold bg-primary hover:bg-primary-hover shadow-sm"
              >
                <UserPlus className="w-3.5 h-3.5 mr-1.5" />
                {busy ? 'Granting Access...' : 'Create Faculty Login'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Authorized Users Table */}
      <Card>
        <CardHeader className="p-5 pb-3 border-b border-hairline flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-bold text-ink">Authorized Faculty Directory</CardTitle>
            <CardDescription className="text-xs text-body mt-0.5">
              Active and suspended access privileges
            </CardDescription>
          </div>
          <Badge variant="mono" className="text-[10px]">
            {activeCount} Active
          </Badge>
        </CardHeader>
        <CardContent className="p-0">
          <Table className="min-w-[640px]">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[35%]">Staff Member</TableHead>
                <TableHead className="w-[30%]">Institutional Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
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
                      {u.role === 'admin' ? 'Administrator' : 'Faculty Operator'}
                    </Badge>
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
    </div>
  );
};

export default UsersView;
