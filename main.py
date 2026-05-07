from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx, asyncio, datetime, os
from collections import defaultdict

app = FastAPI(title="Tribbu Agent Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN", "")

def get_headers():
    return {
        "Authorization": f"Bearer {INTERCOM_TOKEN}",
        "Accept": "application/json",
        "Intercom-Version": "2.11",
        "Content-Type": "application/json",
    }

async def get_admins(client: httpx.AsyncClient) -> dict:
    r = await client.get("https://api.intercom.io/admins", headers=get_headers())
    r.raise_for_status()
    return {str(a["id"]): a["name"] for a in r.json().get("admins", [])}

async def get_all_conversations(client: httpx.AsyncClient, from_ts: int, to_ts: int) -> list:
    all_convs = []
    cursor = None
    while True:
        payload = {
            "query": {
                "operator": "AND",
                "value": [
                    {"field": "created_at", "operator": ">=", "value": from_ts},
                    {"field": "created_at", "operator": "<=", "value": to_ts},
                ]
            },
            "pagination": {"per_page": 150}
        }
        if cursor:
            payload["pagination"]["starting_after"] = cursor
        r = await client.post(
            "https://api.intercom.io/conversations/search",
            headers=get_headers(),
            json=payload
        )
        r.raise_for_status()
        data = r.json()
        convs = data.get("conversations", [])
        all_convs.extend(convs)
        pages = data.get("pages", {})
        nxt = pages.get("next", {})
        cursor = nxt.get("starting_after") if nxt else None
        if not cursor or not convs:
            break
        if len(all_convs) >= 5000:
            break
    return all_convs

@app.get("/api/agents")
async def get_agents(
    date_from: str = Query(default=None, description="YYYY-MM-DD"),
    date_to:   str = Query(default=None, description="YYYY-MM-DD"),
):
    now = datetime.datetime.utcnow()
    if date_from:
        dt_from = datetime.datetime.strptime(date_from, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
    else:
        dt_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_to:
        dt_to = datetime.datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    else:
        dt_to = now.replace(hour=23, minute=59, second=59)
    from_ts = int(dt_from.timestamp()) - 7200
    to_ts   = int(dt_to.timestamp())
    async with httpx.AsyncClient(timeout=60) as client:
        admins_map, convs = await asyncio.gather(
            get_admins(client),
            get_all_conversations(client, from_ts, to_ts)
        )
    stats = defaultdict(lambda: {"conv": 0, "closed": 0, "ratings": [], "rt": []})
    for c in convs:
        aid = str(c.get("admin_assignee_id") or "")
        if not aid:
            continue
        stats[aid]["conv"] += 1
        if c.get("state") == "closed":
            stats[aid]["closed"] += 1
        rating = c.get("conversation_rating")
        if rating and rating.get("rating"):
            stats[aid]["ratings"].append(rating["rating"])
        rt = (c.get("statistics") or {}).get("time_to_admin_reply")
        if rt:
            stats[aid]["rt"].append(rt)
    result = []
    for aid, s in stats.items():
        ratings = s["ratings"]
        csat = round(sum(1 for r in ratings if r >= 4) / len(ratings) * 100, 1) if ratings else None
        rt_sorted = sorted(s["rt"])
        median_rt = rt_sorted[len(rt_sorted) // 2] if rt_sorted else None
        result.append({
            "id":           aid,
            "name":         admins_map.get(aid, f"Agente {aid}"),
            "conv":         s["conv"],
            "closed":       s["closed"],
            "csat":         csat,
            "csat_ratings": len(ratings),
            "median_rt":    median_rt,
        })
    result.sort(key=lambda x: -x["conv"])
    all_ratings = [r for a in result for r in stats[a["id"]]["ratings"]]
    global_csat = round(sum(1 for r in all_ratings if r >= 4) / len(all_ratings) * 100, 1) if all_ratings else None
    return {
        "period":       {"from": date_from or str(dt_from.date()), "to": date_to or str(dt_to.date())},
        "total_convs":  sum(a["conv"] for a in result),
        "total_closed": sum(a["closed"] for a in result),
        "global_csat":  global_csat,
        "agents":       result,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }

@app.get("/health")
def health():
    return {"status": "ok", "token_set": bool(INTERCOM_TOKEN)}
