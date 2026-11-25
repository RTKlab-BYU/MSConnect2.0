import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchAdminUserAccess, inviteAdminUser, queryKeys, resendAdminUserEmail, updateAdminUserAccess } from "@/lib/api/queries";
import type { AdminUserRecord, AppRole, MembershipRole } from "@/lib/api/types";
import { AdminTabs } from "@/features/admin/admin-tabs";

const appRoles: Array<{ value: AppRole; label: string }> = [
  { value: "admin", label: "Administrator" },
  { value: "pi", label: "PI" },
  { value: "researcher", label: "Researcher" },
  { value: "collaborator", label: "Collaborator" },
];
const membershipRoles: Array<{ value: MembershipRole; label: string }> = [
  ...appRoles,
  { value: "facility_manager", label: "Facility manager" },
];
const noLabs: Array<{ id: number; name: string; facility_name: string }> = [];

function RoleSelect<T extends AppRole | MembershipRole>({ label, value, onChange, options }: { label: string; value: T; onChange: (value: T) => void; options: Array<{ value: T; label: string }> }) {
  return (
    <label className="grid gap-1.5 text-sm font-medium">
      {label}
      <select className="h-10 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={value} onChange={(event) => onChange(event.target.value as T)}>
        {options.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}
      </select>
    </label>
  );
}

function accountState(user: AdminUserRecord) {
  if (!user.is_active) return "Invitation pending";
  if (!user.email_verified_at) return "Active · email not verified";
  return "Active";
}

export default function AdminUserAccessPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient();
  const accessQuery = useQuery({ queryKey: queryKeys.adminUserAccess(), queryFn: fetchAdminUserAccess });
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [inviteLab, setInviteLab] = useState("");
  const [inviteGlobalRole, setInviteGlobalRole] = useState<AppRole>("researcher");
  const [inviteMembershipRole, setInviteMembershipRole] = useState<MembershipRole>("researcher");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [labId, setLabId] = useState("");
  const [globalRole, setGlobalRole] = useState<AppRole>("researcher");
  const [membershipRole, setMembershipRole] = useState<MembershipRole>("researcher");
  const [membershipActive, setMembershipActive] = useState(true);
  const [setupUrl, setSetupUrl] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const users = accessQuery.data?.users ?? [];
  const labs = accessQuery.data?.labs ?? noLabs;
  const selected = users.find((user) => user.id === selectedId) ?? null;
  const selectedLabMembership = useMemo(
    () => selected?.memberships.find((membership) => String(membership.lab_id) === labId),
    [selected, labId],
  );

  useEffect(() => {
    if (!inviteLab && labs.length) setInviteLab(String(labs[0].id));
  }, [inviteLab, labs]);

  useEffect(() => {
    if (!selected) return;
    const membership = selected.memberships[0];
    setLabId(String(membership?.lab_id ?? labs[0]?.id ?? ""));
    setGlobalRole(selected.global_role);
    setMembershipRole(membership?.role ?? "researcher");
    setMembershipActive(membership?.active ?? false);
    setError("");
    setNotice("");
  }, [selected, labs]);

  const inviteMutation = useMutation({
    mutationFn: inviteAdminUser,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.adminUserAccess() });
      setUsername("");
      setEmail("");
      setSelectedId(result.user.id);
      setSetupUrl(result.invite_url ?? "");
      setNotice(`Account created for ${result.user.username}. Copy the setup link and share it with them.`);
      setError("");
    },
    onError: (err) => { setError(err instanceof Error ? err.message : "Could not create invitation."); setNotice(""); },
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Select a user first.");
      return updateAdminUserAccess(selected.id, {
        lab_id: Number(labId), global_role: globalRole, membership_role: membershipRole, membership_active: membershipActive,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.adminUserAccess() });
      setNotice("User permissions saved.");
      setError("");
    },
    onError: (err) => { setError(err instanceof Error ? err.message : "Could not update permissions."); setNotice(""); },
  });

  const linkMutation = useMutation({
    mutationFn: resendAdminUserEmail,
    onSuccess: (result) => {
      setSetupUrl(result.account_url ?? "");
      setNotice("Copy the setup link and share it with the user.");
      setError("");
    },
    onError: (err) => { setError(err instanceof Error ? err.message : "Could not send account email."); setNotice(""); },
  });

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5">
      {!embedded ? <header>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Administration</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">User access</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Invite people into a lab, assign their application role, and manage email verification. Admin access here is for MSConnect; Django superuser access remains separately controlled.</p>
      </header> : null}
      {!embedded ? <AdminTabs /> : null}
      <div className="rounded-md border bg-secondary/20 px-4 py-3 text-sm">Create an account, then copy its one-time setup link and share it directly. Email delivery and verification are not enabled yet.</div>

      {error ? <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div> : null}
      {notice ? <div role="status" aria-live="polite" className="rounded-md border bg-secondary/40 px-4 py-3 text-sm">{notice}{setupUrl ? <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]"><Input readOnly aria-label="Account setup link" value={setupUrl} /><Button variant="secondary" onClick={() => void navigator.clipboard.writeText(setupUrl)}><Copy className="h-4 w-4" />Copy link</Button></div> : null}</div> : null}

      <Card>
        <CardHeader>
          <CardTitle>Invite a user</CardTitle>
          <CardDescription>The account stays inactive until the user opens the link and sets a password. No email is sent.</CardDescription>
        </CardHeader>
        <CardContent>
          {labs.length === 0 && !accessQuery.isLoading ? <p className="text-sm text-muted-foreground">Create an active lab before inviting users.</p> : (
            <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" onSubmit={(event) => { event.preventDefault(); inviteMutation.mutate({ username: username.trim(), email: email.trim(), lab: Number(inviteLab), global_role: inviteGlobalRole, membership_role: inviteMembershipRole }); }}>
              <label className="grid gap-1.5 text-sm font-medium">Username<Input autoComplete="off" required value={username} onChange={(event) => setUsername(event.target.value)} /></label>
              <label className="grid gap-1.5 text-sm font-medium">Email<Input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
              <label className="grid gap-1.5 text-sm font-medium">Lab<select className="h-10 rounded-md border border-input bg-background px-3 text-sm" required value={inviteLab} onChange={(event) => setInviteLab(event.target.value)}>{labs.map((lab) => <option key={lab.id} value={lab.id}>{lab.name} · {lab.facility_name}</option>)}</select></label>
              <RoleSelect label="Application-wide role" value={inviteGlobalRole} onChange={setInviteGlobalRole} options={appRoles} />
              <RoleSelect label="Role in this lab" value={inviteMembershipRole} onChange={setInviteMembershipRole} options={membershipRoles} />
              <div className="flex items-end"><Button type="submit" disabled={inviteMutation.isPending || !inviteLab}>{inviteMutation.isPending ? "Creating invitation…" : "Create invitation"}</Button></div>
            </form>
          )}
        </CardContent>
      </Card>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)]">
        <Card>
          <CardHeader><CardTitle>Accounts</CardTitle><CardDescription>{users.length} account{users.length === 1 ? "" : "s"} · select an account to manage access.</CardDescription></CardHeader>
          <CardContent className="p-0">
            {accessQuery.isLoading ? <p className="p-5 text-sm text-muted-foreground">Loading accounts…</p> : accessQuery.isError ? <p role="alert" className="p-5 text-sm text-destructive">{accessQuery.error.message}</p> : users.length === 0 ? <p className="p-5 text-sm text-muted-foreground">No accounts found.</p> : (
              <ul className="divide-y">
                {users.map((user) => (
                  <li key={user.id}>
                    <button type="button" onClick={() => { setSelectedId(user.id); setSetupUrl(""); setNotice(""); }} aria-pressed={selectedId === user.id} className="grid w-full gap-1 px-5 py-3 text-left hover:bg-secondary/40 aria-pressed:bg-secondary/60 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                      <span className="min-w-0"><span className="block truncate text-sm font-medium">{user.username}</span><span className="block truncate text-xs text-muted-foreground">{user.email || "No email"}</span></span>
                      <span className="text-xs text-muted-foreground">{accountState(user)} · {user.global_role}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Permissions</CardTitle><CardDescription>{selected ? `${selected.username} · role and membership` : "Choose an account to edit."}</CardDescription></CardHeader>
          <CardContent>
            {!selected ? <p className="text-sm text-muted-foreground">Select an account from the list.</p> : selected.is_superuser ? (
              <p className="text-sm text-muted-foreground">This is a Django superuser. Change its elevated access through the server’s Django administration process.</p>
            ) : (
              <div className="grid gap-4">
                <div className="text-sm"><div className="font-medium">{accountState(selected)}</div><div className="text-muted-foreground">{selected.email}</div></div>
                <RoleSelect label="Application-wide role" value={globalRole} onChange={setGlobalRole} options={appRoles} />
                <label className="grid gap-1.5 text-sm font-medium">Lab membership<select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={labId} onChange={(event) => setLabId(event.target.value)}>{labs.map((lab) => <option key={lab.id} value={lab.id}>{lab.name} · {lab.facility_name}</option>)}</select></label>
                <RoleSelect label="Role in selected lab" value={membershipRole} onChange={setMembershipRole} options={membershipRoles} />
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={membershipActive} onChange={(event) => setMembershipActive(event.target.checked)} /> Membership active</label>
                {labId && !selectedLabMembership ? <p className="text-xs text-muted-foreground">Saving will add this user to the selected lab.</p> : null}
                <div className="flex flex-wrap gap-2">
                  <Button disabled={saveMutation.isPending || !labId} onClick={() => saveMutation.mutate()}>{saveMutation.isPending ? "Saving…" : "Save permissions"}</Button>
                  {!selected.is_active ? <Button variant="secondary" disabled={linkMutation.isPending} onClick={() => { linkMutation.reset(); linkMutation.mutate(selected.id); }}>{linkMutation.isPending ? "Creating link…" : "Create setup link"}</Button> : null}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
