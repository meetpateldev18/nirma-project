import React, { useCallback, useEffect, useState } from 'react';
import { UserPlus, KeyRound, Power } from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import * as api from '@/lib/api-client';

const errText = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong');

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
      toast.success(`Access given to ${form.name}`);
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
      toast.success(u.is_active ? 'Access removed' : 'Access restored');
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
      toast.success('Password changed');
    } catch (err) {
      toast.error(errText(err));
    }
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Faculty access</h1>
        <p className="text-sm text-body mt-1">Create a login for a faculty member who asked for access. They can only make calls and read their own transcripts.</p>
      </div>

      <Card className="border-hairline">
        <CardHeader className="p-5 pb-2">
          <CardTitle className="text-sm font-semibold text-ink">Give access</CardTitle>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
            <label className="space-y-1.5 text-xs font-medium text-body">Full name
              <Input required minLength={2} value={form.name} onChange={set('name')} placeholder="Dr. A. Shah" />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-body">Email
              <Input required type="email" value={form.email} onChange={set('email')} placeholder="name@nirmauni.ac.in" />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-body">Password
              <Input required minLength={8} type="text" value={form.password} onChange={set('password')} placeholder="min 8 characters" />
            </label>
            <Button type="submit" disabled={busy}><UserPlus className="w-4 h-4 mr-1.5" />Create login</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="border-hairline">
        <CardContent className="p-0">
          <Table className="min-w-[640px]">
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="text-sm text-ink">{u.name}</TableCell>
                  <TableCell className="text-sm text-body">{u.email}</TableCell>
                  <TableCell><Badge variant="secondary" className="text-[10px]">{u.role === 'admin' ? 'Admin' : 'Faculty'}</Badge></TableCell>
                  <TableCell><Badge variant={u.is_active ? 'live' : 'amber'} className="text-[10px]">{u.is_active ? 'Active' : 'Disabled'}</Badge></TableCell>
                  <TableCell className="text-right space-x-1">
                    <Button variant="ghost" size="sm" onClick={() => resetPassword(u)}><KeyRound className="w-3.5 h-3.5 mr-1" />Password</Button>
                    {u.role !== 'admin' && (
                      <Button variant="ghost" size="sm" onClick={() => toggle(u)}><Power className="w-3.5 h-3.5 mr-1" />{u.is_active ? 'Disable' : 'Enable'}</Button>
                    )}
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
