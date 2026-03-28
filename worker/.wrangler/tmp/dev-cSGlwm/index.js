var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// index.js
var index_default = {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduled(event, env));
  }
};
async function handleScheduled(event, env) {
  const POKE_WEBHOOK = env.POKE_WEBHOOK_URL;
  const TOURNAMENT_FILTER = env.TOURNAMENT_FILTER || "IPL";
  const KV2 = env.CRICKET_STATE;
  if (!POKE_WEBHOOK) {
    console.error("POKE_WEBHOOK_URL not configured");
    return;
  }
  try {
    const liveMatchesUrl = "https://www.espncricinfo.com/matches/engine/match/live.json";
    const response = await fetch(liveMatchesUrl);
    const liveMatchesData = await response.json();
    if (!liveMatchesData.matches || liveMatchesData.matches.length === 0) {
      console.log("No live matches found");
      return;
    }
    const filteredMatches = liveMatchesData.matches.filter((match) => {
      const seriesName = match.series?.name || "";
      return seriesName.toUpperCase().includes(TOURNAMENT_FILTER.toUpperCase());
    });
    console.log(`Found ${filteredMatches.length} ${TOURNAMENT_FILTER} matches`);
    for (const match of filteredMatches) {
      await processMatch(match, KV2, POKE_WEBHOOK);
    }
  } catch (error) {
    console.error("Worker error:", error.message);
  }
}
__name(handleScheduled, "handleScheduled");
async function processMatch(matchSummary, KV2, POKE_WEBHOOK) {
  const matchId = matchSummary.match_id;
  const matchUrl = `https://www.espncricinfo.com/matches/engine/match/${matchId}/live.json`;
  try {
    const response = await fetch(matchUrl);
    const matchData = await response.json();
    if (!matchData || !matchData.match) {
      console.log(`No data for match ${matchId}`);
      return;
    }
    const match = matchData.match;
    const matchKey = `match:${matchId}`;
    const previousBallIds = await KV2.get(matchKey, "json") || { processed_balls: [] };
    const processedBalls = new Set(previousBallIds.processed_balls || []);
    const newBallIds = new Set(processedBalls);
    await detectAndPostEvents(
      match,
      processedBalls,
      newBallIds,
      matchId,
      POKE_WEBHOOK
    );
    await KV2.put(
      matchKey,
      JSON.stringify({
        processed_balls: Array.from(newBallIds),
        last_updated: (/* @__PURE__ */ new Date()).toISOString()
      }),
      { expirationTtl: 604800 }
      // 7 days
    );
  } catch (error) {
    console.error(`Error processing match ${matchId}:`, error.message);
  }
}
__name(processMatch, "processMatch");
async function detectAndPostEvents(match, processedBalls, newBallIds, matchId, POKE_WEBHOOK) {
  const matchTitle = getMatchTitle(match);
  if (!match.innings || !Array.isArray(match.innings)) {
    return;
  }
  for (const inning of match.innings) {
    const teamName = inning.team?.name || "Unknown";
    if (!inning.overs || !Array.isArray(inning.overs)) {
      continue;
    }
    for (const over of inning.overs) {
      const overNumber = over.number;
      if (!over.deliveries || !Array.isArray(over.deliveries)) {
        continue;
      }
      for (const ball of over.deliveries) {
        const ballId = `${overNumber}.${(ball.sequence_number || 0) % 10}`;
        if (processedBalls.has(ballId)) {
          continue;
        }
        newBallIds.add(ballId);
        const currentScore = getScoreString(inning);
        const commentary = getCommentary(ball);
        if (ball.wicket) {
          const wicketEvent = {
            match_id: matchId,
            match: matchTitle,
            type: "wicket",
            over: overNumber,
            ball: ballId,
            team: teamName,
            batter: ball.batter?.name || "Unknown",
            commentary,
            score: currentScore,
            timestamp: (/* @__PURE__ */ new Date()).toISOString()
          };
          await postToPokeWebhook(wicketEvent, POKE_WEBHOOK);
        }
        const runs = ball.runs?.runs || 0;
        if (runs >= 4) {
          const boundaryEvent = {
            match_id: matchId,
            match: matchTitle,
            type: runs === 4 ? "4" : "6",
            over: overNumber,
            ball: ballId,
            team: teamName,
            batter: ball.batter?.name || "Unknown",
            runs,
            commentary,
            score: currentScore,
            timestamp: (/* @__PURE__ */ new Date()).toISOString()
          };
          await postToPokeWebhook(boundaryEvent, POKE_WEBHOOK);
        }
        if (over.complete && ball.sequence_number % 10 === 0) {
          const overCompleteEvent = {
            match_id: matchId,
            match: matchTitle,
            type: "over_complete",
            over: overNumber,
            team: teamName,
            runs_in_over: getOverRuns(over),
            wickets_in_over: getOverWickets(over),
            score: currentScore,
            timestamp: (/* @__PURE__ */ new Date()).toISOString()
          };
          await postToPokeWebhook(overCompleteEvent, POKE_WEBHOOK);
        }
      }
    }
  }
  if (match.status_text) {
    const statusKey = `match_status:${matchId}`;
    const previousStatus = await KV.get(statusKey);
    if (previousStatus !== match.status_text) {
      const statusEvent = {
        match_id: matchId,
        match: matchTitle,
        type: "match_status",
        status: match.status_text,
        commentary: match.status_text,
        timestamp: (/* @__PURE__ */ new Date()).toISOString()
      };
      await postToPokeWebhook(statusEvent, POKE_WEBHOOK);
      await KV.put(statusKey, match.status_text, { expirationTtl: 604800 });
    }
  }
}
__name(detectAndPostEvents, "detectAndPostEvents");
function getCommentary(ball) {
  if (ball.commentary) {
    return ball.commentary;
  }
  const batter = ball.batter?.name || "Unknown";
  const bowler = ball.bowler?.name || "Unknown";
  const runs = ball.runs?.runs || 0;
  const extras = ball.runs?.extras || 0;
  let text = `${batter} to ${bowler}`;
  if (ball.wicket) {
    text += ` - ${ball.wicket.wicket_type || "out"}`;
  } else if (runs === 4) {
    text += " - FOUR!";
  } else if (runs === 6) {
    text += " - SIX!";
  } else if (runs > 0) {
    text += ` - ${runs} runs`;
  } else if (extras > 0) {
    text += ` - ${extras} extras`;
  } else {
    text += " - dot";
  }
  return text;
}
__name(getCommentary, "getCommentary");
function getScoreString(inning) {
  if (!inning) return "N/A";
  const team = inning.team?.name || "Team";
  const runs = inning.runs || 0;
  const wickets = inning.wickets || 0;
  let totalDeliveries = 0;
  if (inning.overs && Array.isArray(inning.overs)) {
    for (const over of inning.overs) {
      if (over.deliveries) {
        totalDeliveries += over.deliveries.length;
      }
    }
  }
  const overs = Math.floor(totalDeliveries / 6);
  const balls = totalDeliveries % 6;
  return `${team} ${runs}/${wickets} (${overs}.${balls} ov)`;
}
__name(getScoreString, "getScoreString");
function getMatchTitle(match) {
  if (match.match_title) {
    return match.match_title;
  }
  const team1 = match.teams?.[0]?.name || "Team1";
  const team2 = match.teams?.[1]?.name || "Team2";
  return `${team1} vs ${team2}`;
}
__name(getMatchTitle, "getMatchTitle");
function getOverRuns(over) {
  if (!over.deliveries || !Array.isArray(over.deliveries)) {
    return 0;
  }
  let runs = 0;
  for (const ball of over.deliveries) {
    runs += (ball.runs?.runs || 0) + (ball.runs?.extras || 0);
  }
  return runs;
}
__name(getOverRuns, "getOverRuns");
function getOverWickets(over) {
  if (!over.deliveries || !Array.isArray(over.deliveries)) {
    return 0;
  }
  return over.deliveries.filter((ball) => ball.wicket).length;
}
__name(getOverWickets, "getOverWickets");
async function postToPokeWebhook(event, webhookUrl) {
  try {
    const response = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(event)
    });
    if (!response.ok) {
      console.error(`Poke webhook failed: ${response.status} - ${response.statusText}`);
    } else {
      console.log(`Event posted: ${event.type} for ${event.match}`);
    }
  } catch (error) {
    console.error("Poke webhook error:", error.message);
  }
}
__name(postToPokeWebhook, "postToPokeWebhook");

// ../../../../opt/homebrew/lib/node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// ../../../../opt/homebrew/lib/node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    return Response.json(error, {
      status: 500,
      headers: { "MF-Experimental-Error-Stack": "true" }
    });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-mCrmWj/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = index_default;

// ../../../../opt/homebrew/lib/node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-mCrmWj/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=index.js.map
