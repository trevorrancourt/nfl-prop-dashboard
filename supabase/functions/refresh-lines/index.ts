// refresh-lines: the dashboard's one-tap "Refresh lines" button (added
// 2026-10-16). Starts the "Update dashboard" GitHub Actions workflow, which
// pulls fresh odds and rebuilds the site in about 3-4 minutes.
//
// Lives in Supabase (Edge Functions) so the GitHub token never touches the
// public page. Only signed-in dashboard users whose email is in the
// ALLOWED_EMAILS secret can use it; everyone else just doesn't see the button.
//
// Secrets (Supabase > Edge Functions > Secrets):
//   GH_TOKEN        fine-grained GitHub token: only this repo, Actions read+write
//   ALLOWED_EMAILS  comma-separated, e.g. "you@gmail.com,friend@gmail.com"
//
// GET  -> { allowed, running, run }   (latest workflow run, for the status line)
// POST -> { allowed, started }        (or running:true if one is already going)
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const REPO = "trevorrancourt/nfl-prop-dashboard";
const WORKFLOW = "update.yml";
const CORS = {
  "Access-Control-Allow-Origin": "https://trevorrancourt.github.io",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

function reply(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { ...CORS, "Content-Type": "application/json" } });
}

function github(path: string, init: RequestInit = {}) {
  return fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${Deno.env.get("GH_TOKEN") ?? ""}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "nfl-prop-dashboard",
      "Content-Type": "application/json",
    },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });

  // Who's asking? The page sends the signed-in user's session token.
  const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
  });
  const { data } = await sb.auth.getUser();
  const email = (data?.user?.email ?? "").toLowerCase();
  const allowed = (Deno.env.get("ALLOWED_EMAILS") ?? "")
    .toLowerCase().split(",").map((s) => s.trim()).filter(Boolean);
  if (!email || !allowed.includes(email)) return reply({ allowed: false });

  const runs = await github(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
  if (!runs.ok) return reply({ allowed: true, error: `GitHub said ${runs.status} (check GH_TOKEN)` });
  const r = (await runs.json()).workflow_runs?.[0];
  const run = r ? { status: r.status, conclusion: r.conclusion, created_at: r.created_at, updated_at: r.updated_at } : null;
  const running = !!r && r.status !== "completed";

  if (req.method === "GET") return reply({ allowed: true, running, run });
  // One at a time: a second tap while a refresh is going just follows that one.
  if (running) return reply({ allowed: true, started: false, running: true, run });

  const go = await github(`/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main" }),
  });
  if (go.status !== 204) return reply({ allowed: true, error: `GitHub said ${go.status} (check GH_TOKEN)` });
  return reply({ allowed: true, started: true });
});
