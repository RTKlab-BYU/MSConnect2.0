import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Plus, Send } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  createProjectAssistantThread,
  fetchProjectAssistant,
  fetchProjectAssistantThread,
  sendProjectAssistantMessage,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";

export function ProjectAssistantPanel({ projectId }: { projectId: number }) {
  const [threadId, setThreadId] = useState<number | null>(null);
  const [modelIndex, setModelIndex] = useState(0);
  const [draft, setDraft] = useState("");
  const indexQuery = useQuery({
    queryKey: ["project-assistant", projectId],
    queryFn: () => fetchProjectAssistant(projectId),
  });
  const threadQuery = useQuery({
    queryKey: ["project-assistant", projectId, threadId],
    queryFn: () => fetchProjectAssistantThread(projectId, threadId!),
    enabled: threadId !== null,
  });
  const models = indexQuery.data?.models ?? [];
  const selectedModel = models[modelIndex] ?? models[0];
  const createMutation = useMutation({
    mutationFn: () => {
      if (!selectedModel) throw new Error("No assistant model is configured.");
      return createProjectAssistantThread(projectId, selectedModel.provider, selectedModel.model);
    },
    onSuccess: async (thread) => {
      setThreadId(thread.id);
      await queryClient.invalidateQueries({ queryKey: ["project-assistant", projectId] });
    },
  });
  const sendMutation = useMutation({
    mutationFn: () => {
      if (threadId === null) throw new Error("Start a conversation first.");
      return sendProjectAssistantMessage(projectId, threadId, draft.trim());
    },
    onSuccess: async () => {
      setDraft("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project-assistant", projectId, threadId] }),
        queryClient.invalidateQueries({ queryKey: ["project-assistant", projectId] }),
      ]);
    },
  });
  const threads = indexQuery.data?.threads ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-primary/10 p-2 text-primary"><Bot className="h-5 w-5" /></div>
          <div>
            <CardTitle>Project assistant</CardTitle>
            <CardDescription>Private to your account. It can explain the visible project record and existing outputs; it cannot change records or launch work.</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="grid content-start gap-3">
          {models.length ? (
            <>
              <label className="grid gap-1 text-xs font-bold uppercase text-muted-foreground">
                Model
                <select className="h-10 rounded-md border bg-background px-3 text-sm font-normal normal-case text-foreground" value={models.indexOf(selectedModel!)} onChange={(event) => setModelIndex(Number(event.target.value))}>
                  {models.map((item, index) => <option key={`${item.provider}:${item.model}`} value={index}>{item.provider} · {item.model}</option>)}
                </select>
              </label>
              <Button variant="secondary" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                <Plus className="h-4 w-4" /> New conversation
              </Button>
            </>
          ) : (
            <div className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
              No assistant model is enabled. An administrator must configure a provider key and model allowlist.
            </div>
          )}
          <div className="grid gap-1">
            {threads.map((thread) => (
              <button key={thread.id} type="button" onClick={() => setThreadId(thread.id)} className={`rounded-lg px-3 py-2 text-left text-sm ${threadId === thread.id ? "bg-primary text-primary-foreground" : "hover:bg-secondary"}`}>
                <span className="block truncate font-semibold">{thread.title || "New conversation"}</span>
                <span className="block truncate text-xs opacity-75">{thread.provider} · {thread.model}</span>
              </button>
            ))}
          </div>
        </aside>
        <section className="grid min-h-[420px] grid-rows-[1fr_auto] gap-3">
          <div className="max-h-[520px] min-h-[260px] space-y-3 overflow-y-auto rounded-xl border bg-muted/20 p-4" aria-live="polite">
            {threadQuery.data?.messages?.map((message) => (
              <div key={message.id} className={`max-w-[90%] whitespace-pre-wrap rounded-xl px-4 py-3 text-sm leading-6 ${message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "border bg-card"}`}>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-wide opacity-70">{message.role === "assistant" ? `${message.provider} · ${message.model}` : "You"}</div>
                {message.content}
              </div>
            ))}
            {!threadId ? <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">Start a conversation to ask about this project’s worklist, runs, QC, processing, or results.</div> : null}
            {threadQuery.isFetching ? <div className="text-xs text-muted-foreground">Updating conversation…</div> : null}
          </div>
          <form className="grid gap-2" onSubmit={(event) => { event.preventDefault(); if (draft.trim()) sendMutation.mutate(); }}>
            <Textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask a question about this project…" maxLength={12000} disabled={!threadId || sendMutation.isPending} className="min-h-24 resize-y" />
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-muted-foreground">Project context only · {draft.length}/12,000</span>
              <Button type="submit" disabled={!threadId || !draft.trim() || sendMutation.isPending}><Send className="h-4 w-4" />{sendMutation.isPending ? "Thinking…" : "Send"}</Button>
            </div>
            {sendMutation.error instanceof Error ? <div role="alert" className="text-sm text-destructive">{sendMutation.error.message}</div> : null}
          </form>
        </section>
      </CardContent>
    </Card>
  );
}
