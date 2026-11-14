/** In-memory stand-in state for mock mode. */

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function notFound(path: string): Response {
  return json(404, { message: `No mock route for ${path}` });
}

export function resetAdminMockState(): void {
  // Routes reset their own module state. This hook stays so callers can ask.
}

export function setMockStaging(on: boolean): void {
  void on;
}
