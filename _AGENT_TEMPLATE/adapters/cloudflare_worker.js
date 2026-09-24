/**
 * Cloudflare Workers Deployment Adapter
 *
 * Pattern: Minimal JavaScript wrapper that delegates to Python core logic via subprocess.
 *
 * Note: For production, this should:
 * 1. Call your core logic via Worker-to-Python bridge (GCP Cloud Functions, etc.)
 * 2. Or reimplement core logic in JavaScript/TypeScript
 * 3. Or use a Python HTTP adapter and call it from the Worker
 *
 * This template shows the recommended pattern for delegating to core logic.
 */

/**
 * Handle incoming requests
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // Parse query parameters and request body
    const searchParams = url.searchParams;
    let body = null;
    if (method !== "GET" && method !== "HEAD") {
      try {
        body = await request.json();
      } catch (e) {
        return jsonResponse({ status: "error", error: "Invalid JSON" }, 400);
      }
    }

    // Route to appropriate handler
    if (path === "/health") {
      return handleHealth(env, ctx);
    } else if (path === "/describe") {
      return handleDescribe(env, ctx);
    } else if (path === "/process" && method === "POST") {
      return handleProcess(body, env, ctx);
    } else if (path === "/info") {
      return handleInfo(env, ctx);
    } else if (path === "/") {
      return handleRoot(env, ctx);
    } else {
      return jsonResponse({ error: "Not found" }, 404);
    }
  },
};

/**
 * Health check endpoint
 */
async function handleHealth(env, ctx) {
  // In production, call your core logic here
  // Example: await callCoreService(env, "health")
  return jsonResponse({
    status: "ok",
    agent: env.AGENT_NAME || "agent",
    version: "0.1.0",
    platform: "cloudflare-worker",
  });
}

/**
 * Describe agent capabilities
 */
async function handleDescribe(env, ctx) {
  // In production, call your core logic here
  // Example: const desc = await callCoreService(env, "describe")
  return jsonResponse({
    name: env.AGENT_NAME || "agent",
    version: "0.1.0",
    platform: "cloudflare-worker",
    capabilities: [],
    inputs: {},
    outputs: {
      status: "str (ok|error)",
      error: "str (optional)",
    },
  });
}

/**
 * Main processing endpoint
 *
 * In production, this should:
 * 1. Call your Python core logic via HTTP bridge
 * 2. Or call a Cloud Function that wraps your core logic
 * 3. Or reimplement the core logic in JavaScript
 *
 * Pattern:
 *   const result = await callCoreService(env, "process", payload);
 *   return jsonResponse(result);
 */
async function handleProcess(payload, env, ctx) {
  try {
    if (!payload) {
      return jsonResponse(
        { status: "error", error: "No payload provided" },
        400
      );
    }

    // Validate required fields (customize based on your agent)
    if (!payload.input) {
      return jsonResponse(
        { status: "error", error: "Missing 'input' field" },
        400
      );
    }

    // PRODUCTION: Replace this with actual core logic call
    // const result = await callCoreService(env, "process", payload);
    // return jsonResponse(result);

    // STUB: Echo-style placeholder for demonstration
    const result = {
      status: "ok",
      data: {
        message: "Processing in Cloudflare Worker",
        received: payload,
        platform: "cloudflare-worker",
      },
    };

    return jsonResponse(result);
  } catch (error) {
    console.error("Process error:", error);
    return jsonResponse(
      {
        status: "error",
        error: error.message || "Processing failed",
      },
      500
    );
  }
}

/**
 * Agent info endpoint
 */
async function handleInfo(env, ctx) {
  return jsonResponse({
    name: env.AGENT_NAME || "agent",
    version: "0.1.0",
    platform: "cloudflare-worker",
    status: "running",
  });
}

/**
 * Root endpoint
 */
async function handleRoot(env, ctx) {
  return jsonResponse({
    agent: env.AGENT_NAME || "agent",
    version: "0.1.0",
    platform: "cloudflare-worker",
    endpoints: {
      health: "/health",
      describe: "/describe",
      process: "/process (POST)",
      info: "/info",
    },
  });
}

/**
 * PRODUCTION PATTERN: Call core logic via HTTP bridge
 *
 * Example: If your core is exposed via a Cloud Function or API Gateway
 */
async function callCoreService(env, operation, payload = null) {
  const coreUrl = env.CORE_SERVICE_URL;
  if (!coreUrl) {
    throw new Error("CORE_SERVICE_URL not configured");
  }

  const url = `${coreUrl}/${operation}`;
  const options = {
    method: payload ? "POST" : "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.CORE_API_KEY}`,
    },
  };

  if (payload) {
    options.body = JSON.stringify(payload);
  }

  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(
      `Core service error: ${response.status} ${response.statusText}`
    );
  }

  return await response.json();
}

/**
 * Helper: JSON response
 */
function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
