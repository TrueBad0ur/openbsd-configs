import asyncio
import aiohttp
import sys
import time
from collections import Counter

URL = sys.argv[1] if len(sys.argv) > 1 else "http://target"
CONCURRENT = 200
TOTAL = 10000

stats = Counter()
start = time.time()

async def flood(session, sem, i):
    async with sem:
        try:
            async with session.get(
                URL,
                timeout=aiohttp.ClientTimeout(total=2),
                headers={"Connection": "close"}
            ) as r:
                stats[f"HTTP {r.status}"] += 1
                if i % 100 == 0:
                    elapsed = time.time() - start
                    rps = i / elapsed if elapsed > 0 else 0
                    print(f"[{i}/{TOTAL}] status={r.status} | rps={rps:.0f} | stats={dict(stats)}")
        except aiohttp.ClientConnectorError:
            stats["CONN_REFUSED"] += 1
            if i % 100 == 0:
                print(f"[{i}/{TOTAL}] BLOCKED (connection refused) | stats={dict(stats)}")
        except asyncio.TimeoutError:
            stats["TIMEOUT"] += 1
            if i % 100 == 0:
                print(f"[{i}/{TOTAL}] TIMEOUT | stats={dict(stats)}")
        except Exception as e:
            stats[f"ERR:{type(e).__name__}"] += 1
            if i % 100 == 0:
                print(f"[{i}/{TOTAL}] ERROR: {e} | stats={dict(stats)}")

async def main():
    sem = asyncio.Semaphore(CONCURRENT)
    async with aiohttp.ClientSession() as session:
        tasks = [flood(session, sem, i) for i in range(TOTAL)]
        await asyncio.gather(*tasks)

    elapsed = time.time() - start
    print("\n=== RESULTS ===")
    print(f"total:    {TOTAL}")
    print(f"elapsed:  {elapsed:.1f}s")
    print(f"avg rps:  {TOTAL/elapsed:.0f}")
    for k, v in sorted(stats.items()):
        pct = v / TOTAL * 100
        print(f"  {k:<20} {v:>6} ({pct:.1f}%)")

asyncio.run(main())
