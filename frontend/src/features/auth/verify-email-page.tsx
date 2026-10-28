import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function VerifyEmailPage() {
  const { token = "" } = useParams();
  const [state, setState] = useState<{ status: "loading" | "success" | "error"; message: string }>({ status: "loading", message: "Checking your verification link…" });

  useEffect(() => {
    let active = true;
    fetch(`/accounts/verify-email/${encodeURIComponent(token)}/`, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || data.token?.[0] || "This verification link is invalid or has expired. Ask an administrator to send another.");
        if (active) setState({ status: "success", message: "Your email is verified. You can continue to your MSConnect workspace." });
      })
      .catch((error: unknown) => {
        if (active) setState({ status: "error", message: error instanceof Error ? error.message : "Could not verify this email." });
      });
    return () => { active = false; };
  }, [token]);

  return (
    <main className="grid min-h-screen place-items-center bg-background p-4">
      <Card className="w-full max-w-lg">
        <CardHeader><CardTitle>Email verification</CardTitle><CardDescription>MSConnect account access</CardDescription></CardHeader>
        <CardContent className="grid gap-4">
          <p role={state.status === "error" ? "alert" : "status"} aria-live="polite" className="text-sm">{state.message}</p>
          {state.status === "success" ? <Button asChild><Link to="/projects">Continue to projects</Link></Button> : null}
          {state.status === "error" ? <Button variant="secondary" asChild><a href="/accounts/login/">Sign in or contact an administrator</a></Button> : null}
        </CardContent>
      </Card>
    </main>
  );
}
