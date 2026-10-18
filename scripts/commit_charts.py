"""Draw the 30-day commit charts shown in the profile README.

assets/commits-all.svg       every public, non-fork repo owned by USER
assets/commits-leetcode.svg  leetcode-solutions (LeetHub commits each accepted solve)

Only commits GitHub links to USER's account are counted, on each repo's default branch,
bucketed by UTC author date. Standard library only, so the workflow needs no
pip install.
"""

import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER = "rounak251"
LEETCODE_REPO = "leetcode-solutions"
DAYS = 30
OUT = Path(__file__).resolve().parent.parent / "assets"

# Palette shared with the README badges and Mermaid diagrams.
BG, PANEL, GRID = "#020617", "#0F172A", "#1E293B"
ACCENT, ACCENT_DIM, TEXT, MUTED = "#4ADE80", "#166534", "#DCFCE7", "#64748B"


def api(path, **params):
    url = f"https://api.github.com{path}?{urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-charts",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as resp:
        return json.load(resp)


def paged(path, **params):
    page = 1
    while True:
        batch = api(path, per_page=100, page=page, **params)
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def public_repos():
    for repo in paged(f"/users/{USER}/repos", type="owner"):
        if not repo["private"] and not repo["fork"]:
            yield repo["name"]


def commit_days(repo, since, until):
    # The API's author=<login> filter skips commits made with the noreply
    # address, so filter on the linked account instead.
    try:
        for c in paged(f"/repos/{USER}/{repo}/commits", since=since, until=until):
            if (c.get("author") or {}).get("login") == USER:
                yield c["commit"]["author"]["date"][:10]
    except HTTPError as err:
        if err.code in (404, 409):  # deleted mid-run, or empty repo
            print(f"skip {repo}: HTTP {err.code}", file=sys.stderr)
            return
        raise


def render(title, days, counts, link_text):
    w, h = 900, 250
    left, right, top, bottom = 48, 20, 58, 46
    plot_w, plot_h = w - left - right, h - top - bottom
    peak = max(max(counts.values(), default=0), 1)
    # Round the axis up to a tidy number so gridlines land on integers.
    step = next(s for s in (1, 2, 5, 10, 20, 50, 100, 200, 500) if peak / s <= 4)
    ymax = step * -(-peak // step)
    slot = plot_w / len(days)
    bar_w = slot * 0.62
    total = sum(counts[d.isoformat()] for d in days)
    active = sum(1 for d in days if counts[d.isoformat()])

    s = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{title}: {total} commits in the last {len(days)} days">',
        f"<title>{title}: {total} commits in the last {len(days)} days</title>",
        "<style>text{font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}</style>",
        f'<rect width="{w}" height="{h}" rx="10" fill="{BG}"/>',
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="9" fill="none" stroke="{GRID}"/>',
        f'<text x="{left}" y="30" fill="{ACCENT}" font-size="15" font-weight="700">&gt; {title}</text>',
        f'<text x="{w - right}" y="30" fill="{TEXT}" font-size="13" text-anchor="end">'
        f'{total} commits · {active}/{len(days)} active days</text>',
    ]
    for v in range(0, ymax + 1, step):
        y = top + plot_h - plot_h * v / ymax
        s.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
        s.append(f'<text x="{left - 8}" y="{y + 4:.1f}" fill="{MUTED}" font-size="11" text-anchor="end">{v}</text>')
    for i, d in enumerate(days):
        n = counts[d.isoformat()]
        x = left + i * slot + (slot - bar_w) / 2
        if n:
            bh = max(plot_h * n / ymax, 3)
            s.append(
                f'<rect x="{x:.1f}" y="{top + plot_h - bh:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                f'rx="2" fill="{ACCENT}"><title>{d.isoformat()}: {n}</title></rect>'
            )
        else:
            s.append(f'<rect x="{x:.1f}" y="{top + plot_h - 2}" width="{bar_w:.1f}" height="2" fill="{ACCENT_DIM}"/>')
        if i % 5 == 0 or i == len(days) - 1:
            s.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{top + plot_h + 18}" fill="{MUTED}" font-size="11" '
                f'text-anchor="middle">{d.strftime("%d %b")}</text>'
            )
    s.append(
        f'<text x="{left}" y="{h - 10}" fill="{MUTED}" font-size="11">{link_text} · UTC · '
        f'updated {days[-1].isoformat()}</text>'
    )
    s.append("</svg>")
    return "\n".join(s) + "\n"


def main():
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]
    since = f"{days[0].isoformat()}T00:00:00Z"
    until = f"{(today + timedelta(days=1)).isoformat()}T00:00:00Z"

    per_repo = {repo: Counter(commit_days(repo, since, until)) for repo in public_repos()}
    everything = sum(per_repo.values(), Counter())
    leetcode = per_repo.get(LEETCODE_REPO, Counter())

    OUT.mkdir(exist_ok=True)
    (OUT / "commits-all.svg").write_text(
        render("commit_log --all-repos", days, everything, f"{len(per_repo)} public repos")
    )
    (OUT / "commits-leetcode.svg").write_text(
        render("commit_log --repo leetcode-solutions", days, leetcode, "LeetHub commits every accepted solve")
    )
    for name, c in sorted(per_repo.items()):
        if c:
            print(f"{name}: {sum(c.values())}")


if __name__ == "__main__":
    main()
