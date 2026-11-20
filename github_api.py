import httpx

API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "RepoPilot-Bot",
}


def _h(token=None):
    h = dict(HEADERS)
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def get(path, token=None, params=None):
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.get(f"{API}{path}", headers=_h(token), params=params)


async def post(path, token, json):
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.post(f"{API}{path}", headers=_h(token), json=json)


async def put(path, token, json=None):
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.put(f"{API}{path}", headers=_h(token), json=json)


async def delete(path, token):
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.delete(f"{API}{path}", headers=_h(token))