import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { signupAccount } from "@/lib/api/queries";

export default function SignupPage() {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    institution_name: "",
    lab_name: "",
  });

  const signupMutation = useMutation({
    mutationFn: signupAccount,
    onSuccess: () => {
      navigate("/submissions/new");
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Could not create account.");
    },
  });

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(20,184,166,0.18),_transparent_34%),radial-gradient(circle_at_top_right,_rgba(15,118,110,0.15),_transparent_28%),linear-gradient(180deg,_hsl(var(--background)),_hsl(var(--muted)/0.25))] p-4 md:p-8">
      <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-4xl items-center">
        <Card className="w-full overflow-hidden border-2 border-foreground/10 shadow-2xl shadow-foreground/10">
          <CardHeader className="border-b bg-secondary/30">
            <CardTitle className="text-3xl">Create a collaborator account</CardTitle>
            <CardDescription>
              Use this to provision a lab-scoped workspace, verify your email, and submit intake requests directly.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 p-6 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium">
              Username
              <Input value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Email
              <Input type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Password
              <Input type="password" value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Institution
              <Input value={form.institution_name} onChange={(event) => setForm((current) => ({ ...current, institution_name: event.target.value }))} />
            </label>
            <label className="grid gap-2 text-sm font-medium md:col-span-2">
              Lab name
              <Input value={form.lab_name} onChange={(event) => setForm((current) => ({ ...current, lab_name: event.target.value }))} />
            </label>
            <div className="md:col-span-2 flex flex-wrap items-center gap-3">
              <Button
                onClick={() => signupMutation.mutate(form)}
                disabled={signupMutation.isPending || !form.username || !form.email || !form.password}
              >
                {signupMutation.isPending ? "Creating..." : "Create account"}
              </Button>
              <Button variant="secondary" asChild>
                <a href="/accounts/login/">Use existing login</a>
              </Button>
            </div>
            {error ? <div className="md:col-span-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</div> : null}
            <div className="md:col-span-2 rounded-lg border bg-background/70 p-4 text-sm text-muted-foreground">
              Verification email is queued when email delivery is configured. In development, the account is provisioned immediately and can be used to submit requests.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
