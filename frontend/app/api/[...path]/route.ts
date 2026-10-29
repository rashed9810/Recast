/**
 * Forwards /api/* to the Python backend and streams the response back
 * unchanged. Unlike Next's rewrite proxy this has no 30-second limit, so slow
 * local models work, and progress events reach the browser as they happen.
 */
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 1800;

const BACKEND = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function forward(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${BACKEND}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
      body: hasBody ? await req.arrayBuffer() : undefined,
      signal: req.signal, // browser pressed Stop → backend stops too
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: `Can't reach the Recast backend at ${BACKEND}. Start it with: uvicorn app.main:app --port 8000` },
      { status: 503 },
    );
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-cache",
      "x-accel-buffering": "no",
    },
  });
}

export { forward as GET, forward as POST, forward as PUT, forward as DELETE };
