import React, { useState } from 'react';
import { PhoneCall, ShieldCheck, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useAuth } from '@/lib/auth-context';
import { ApiError } from '@/lib/api-client';

export const LoginView: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState('admin@nirmauni.ac.in');
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
      setError(err instanceof ApiError ? err.message : 'Unable to reach the AI Call Agent backend.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center px-4 font-sans antialiased">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center space-y-2">
          <div className="w-12 h-12 rounded-md bg-gradient-to-br from-primary to-primary-deep flex items-center justify-center shadow-lg shadow-orange-950/40 border border-orange-400/20">
            <PhoneCall className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-lg font-semibold text-ink tracking-tight">NIRMA UNIVERSITY</h1>
          <p className="text-xs text-mute font-mono">AI Call Agent · Staff Mission Control</p>
        </div>

        <Card className="bg-canvas-soft border-hairline">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold text-ink">Staff Sign In</CardTitle>
            <CardDescription className="text-xs text-body">
              Authenticate with your institutional staff credentials
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-3.5">
              <div className="space-y-1.5">
                <label htmlFor="login-email" className="text-xs font-medium text-body">
                  Institutional Email
                </label>
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="operator@nirmauni.ac.in"
                  className="bg-canvas-elevated text-ink"
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
                  className="bg-canvas-elevated text-ink"
                />
              </div>

              {error && (
                <div role="alert" className="text-[11px] text-red-400 bg-red-950/30 border border-red-900/40 rounded px-2.5 py-1.5">
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
          </CardContent>
        </Card>

        <p className="text-center text-[10px] text-mute font-mono">
          Seed credentials (local dev): admin@nirmauni.ac.in · password set via backend/seeds.py
        </p>
      </div>
    </div>
  );
};

export default LoginView;
