/**
 * Neon Function: deployment status probe.
 *
 * Reports which Neon services are configured for this branch. It deliberately
 * returns presence booleans and never any value, so the endpoint is safe to
 * expose: a token, connection string or secret must not leak through a status
 * URL.
 *
 * Zero dependencies by design -- a Neon Function is any default export with a
 * `fetch(request)` method returning a Response, so this deploys without a build
 * step or an npm install.
 */

type ServiceStatus = {
  configured: boolean;
};

function configured(...names: string[]): ServiceStatus {
  return { configured: names.every((name) => Boolean(process.env[name])) };
}

export default {
  fetch(request: Request): Response {
    const url = new URL(request.url);

    if (url.pathname === "/healthz") {
      return Response.json({ status: "ok" });
    }

    const services = {
      postgres: configured("DATABASE_URL"),
      auth: configured("NEON_AUTH_BASE_URL", "NEON_AUTH_JWKS_URL"),
      aiGateway: configured("NEON_AI_GATEWAY_BASE_URL", "NEON_AI_GATEWAY_TOKEN"),
      realtime: configured("NEON_REALTIME_URL", "NEON_REALTIME_SECRET"),
    };

    return Response.json(
      {
        status: "ok",
        branch: process.env.NEON_BRANCH ?? null,
        services,
        time: new Date().toISOString(),
      },
      { headers: { "cache-control": "no-store" } },
    );
  },
};