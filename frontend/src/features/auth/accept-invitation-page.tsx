import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { acceptInvitation } from "@/lib/api/queries";

export default function AcceptInvitationPage() {
  const { uid = "", token = "" } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const acceptMutation = useMutation({
    mutationFn: acceptInvitation,
    onSuccess: () => navigate("/projects", { replace: true }),
    onError: (reason) => setError(reason instanceof Error ? reason.message : "Could not accept this invitation."),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) { setError("The passwords do not match."); return; }
    acceptMutation.mutate({ uid, token, password });
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background p-4">
      <Card className="w-full max-w-lg">
        <CardHeader><CardTitle>Finish account setup</CardTitle><CardDescription>Choose a password to activate your account and verify this email address.</CardDescription></CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={submit}>
            <label className="grid gap-1.5 text-sm font-medium">Password<Input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} /><span className="text-xs font-normal text-muted-foreground">Use at least 12 characters. The server also checks its configured password rules.</span></label>
            <label className="grid gap-1.5 text-sm font-medium">Confirm password<Input type="password" autoComplete="new-password" minLength={12} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
            {error ? <p role="alert" className="break-words text-sm text-destructive">{error}</p> : null}
            <Button type="submit" disabled={acceptMutation.isPending}>{acceptMutation.isPending ? "Activating account…" : "Set password and continue"}</Button>
            <p className="text-xs text-muted-foreground">Invitation expired? <Link className="underline underline-offset-2" to="/accounts/login/">Contact your MSConnect administrator</Link> to resend it.</p>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
