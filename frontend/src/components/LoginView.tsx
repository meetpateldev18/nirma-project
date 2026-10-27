import React, { useState } from 'react';
import { PhoneCall, ShieldCheck, Loader2, KeyRound } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useAuth } from '@/lib/auth-context';
import { ApiError } from '@/lib/api-client';

export const LoginView: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to reach the Nirma Calling Assistant backend.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary via-[#5B82F2] to-[#BCCBFA] flex items-center justify-center px-4 py-8 font-sans antialiased">
      <div className="w-full max-w-sm space-y-6 bg-white rounded-3xl p-6 sm:p-8 shadow-xl">
        <div className="flex flex-col items-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-primary flex items-center justify-center">
            <PhoneCall className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-primary tracking-tight">NIRMA CALLING ASSISTANT</h1>
          <p className="text-xs text-mute">Nirma Calling Assistant</p>
        </div>

        <Card className="border-0 shadow-none">
          <CardHeader className="p-0 pb-3">
            <CardTitle className="text-sm font-semibold text-ink">Sign in</CardTitle>
            <CardDescription className="text-xs text-body">
              Use the login given to you by the administrator.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <form onSubmit={handleSubmit} className="space-y-3.5">
              <div className="space-y-1.5">
                <label htmlFor="login-email" className="text-xs font-medium text-body">
                  Email
                </label>
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@nirmauni.ac.in"
                  className="text-ink"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="login-password" className="text-xs font-medium text-body">
                  Password
                </label>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="text-ink"
                />
              </div>

              {error && (
                <div role="alert" className="text-[11px] text-red-700 bg-red-50 border border-red-200 rounded px-2.5 py-1.5">
                  {error}
                </div>
              )}

              <Button type="submit" variant="default" className="w-full text-xs font-semibold" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Signing in...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> Sign In
                  </>
                )}
              </Button>
            </form>

            <div className="mt-4 pt-3.5 border-t border-hairline/80">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-medium text-mute flex items-center gap-1">
                  <KeyRound className="w-3 h-3 text-primary" /> Demo Credentials
                </span>
                <span className="text-[10px] text-mute font-mono">click to fill</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEmail('admin@nirmauni.ac.in');
                    setPassword('Nirma@123');
                    setError(null);
                  }}
                  className="flex flex-col text-left p-2 rounded-xl border border-hairline bg-canvas-subtle hover:bg-canvas-soft hover:border-primary/40 transition-colors"
                >
                  <span className="text-[11px] font-semibold text-ink">Administrator</span>
                  <span className="text-[10px] font-mono text-mute truncate">admin@nirmauni.ac.in</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setEmail('operator@nirmauni.ac.in');
                    setPassword('Nirma@123');
                    setError(null);
                  }}
                  className="flex flex-col text-left p-2 rounded-xl border border-hairline bg-canvas-subtle hover:bg-canvas-soft hover:border-primary/40 transition-colors"
                >
                  <span className="text-[11px] font-semibold text-ink">Faculty / Operator</span>
                  <span className="text-[10px] font-mono text-mute truncate">operator@nirmauni.ac.in</span>
                </button>
              </div>
            </div>
          </CardContent>
        </Card>

        <p className="text-center text-[11px] text-mute">
          No account? Ask the system administrator in person.
        </p>
      </div>
    </div>
  );
};

export default LoginView;
