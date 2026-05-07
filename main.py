from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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

async def fetch_page(client, payload):
    r = await client.post(
        "https://api.intercom.io/conversations/search",
        headers=get_headers(), json=payload
    )
    r.raise_for_status()
    return r.json()

async def get_all_conversations(client, from_ts, to_ts):
    # Use updated_at filter — much faster than created_at for recent data
    payload = {
        "query": {
            "operator": "AND",
            "value": [
                {"field": "updated_at", "operator": ">=", "value": from_ts},
                {"field": "updated_at", "operator": "<=", "value": to_ts},
                {"field": "created_at", "operator": ">=", "value": from_ts},
                {"field": "created_at", "operator": "<=", "value": to_ts},
            ]
        },
        "pagination": {"per_page": 150}
    }

    first = await fetch_page(client, payload)
    all_convs = first.get("conversations", [])
    pages = first.get("pages", {})
    total_pages = min(pages.get("total_pages", 1), 15)  # max 15 pages = 2250 convs

    cursor = pages.get("next", {}).get("starting_after")
    page = 2

    # Fetch remaining pages concurrently in batches of 5
    while cursor and page <= total_pages:
        batch_tasks = []
        batch_cursors = [cursor]

        # We can't easily batch without cursors, so fetch sequentially but fast
        p = {**payload, "pagination": {"per_page": 150, "starting_after": cursor}}
        data = await fetch_page(client, p)
        convs = data.get("conversations", [])
        all_convs.extend(convs)
        nxt = data.get("pages", {}).get("next", {})
        cursor = nxt.get("starting_after") if nxt else None
        page += 1

    return all_convs

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "<h1>Dashboard no encontrado</h1>"

@app.get("/api/agents")
async def get_agents(
    date_from: str = Query(default=None),
    date_to:   str = Query(default=None),
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

    # Madrid UTC+2
    from_ts = int(dt_from.timestamp()) - 7200
    to_ts   = int(dt_to.timestamp())

    async with httpx.AsyncClient(timeout=55) as client:
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
    return {"status": "ok", "token_set": bool(INTERCOM_TOKEN)
