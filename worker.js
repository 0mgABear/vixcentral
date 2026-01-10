// This is the file that is the brains behind the Cloudflare Cron Trigger
// It is not needed in the repository for any Github Actions, but has been included for sharing purposes

export default {
  async scheduled(event, env, ctx) {
    const now = new Date(event.scheduledTime); // UTC timestamp of the cron firing
    const utcHour = now.getUTCHours();

    const nyIsDst = isNyDst(now);

    const shouldRun =
      (nyIsDst && utcHour === 13) || (!nyIsDst && utcHour === 14);

    if (!shouldRun) return;

    ctx.waitUntil(triggerGithub(env));
  },
};

async function triggerGithub(env) {
  const owner = env.GH_OWNER;
  const repo = env.GH_REPO;
  const workflow = env.GH_WORKFLOW; // e.g. "vixbot.yml"
  const ref = env.GH_REF || "main";

  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GH_TOKEN}`,
      "User-Agent": "cloudflare-worker-vixbot-dispatcher",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `GitHub dispatch failed: ${res.status} ${res.statusText} ${text}`
    );
  }
}

function isNyDst(now) {
  const jan = new Date(Date.UTC(now.getUTCFullYear(), 0, 1));
  const offNow = tzOffsetMinutes("America/New_York", now);
  const offJan = tzOffsetMinutes("America/New_York", jan);
  return offNow !== offJan;
}

function tzOffsetMinutes(tz, dateObj) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(dateObj);

  const get = (t) => parts.find((p) => p.type === t).value;

  // Interpret those tz-local parts as UTC, then compare to real UTC timestamp.
  const asUtc = Date.UTC(
    Number(get("year")),
    Number(get("month")) - 1,
    Number(get("day")),
    Number(get("hour")),
    Number(get("minute")),
    Number(get("second"))
  );

  return Math.round((asUtc - dateObj.getTime()) / 60000);
}
