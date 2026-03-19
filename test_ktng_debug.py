"""document.xml 응답 디버깅"""
import asyncio, sys, httpx
sys.stdout.reconfigure(encoding="utf-8")

from open_proxy_mcp.dart.client import DartClient

async def main():
    client = DartClient()
    async with httpx.AsyncClient(verify=False) as http:
        url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={client.api_key}&rcept_no=20260318001515"
        resp = await http.get(url, timeout=30)
        print(f"Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type')}")
        print(f"Content length: {len(resp.content)}")
        print(f"First 500 bytes:\n{resp.content[:500]}")

asyncio.run(main())
