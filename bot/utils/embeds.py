from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord

from bot.models.ctf import CTF, CTFStatus

# All CTF time labels are rendered in KST so the team sees a single,
# unambiguous wall-clock value regardless of each user's Discord locale.
KST = timezone(timedelta(hours=9), name="KST")


def _aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (treat naive as UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def fmt_kst(dt: datetime) -> str:
    """Format an absolute time as 'YYYY-MM-DD HH:MM KST' (24-hour)."""
    return _aware(dt).astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def fmt_kst_with_relative(dt: datetime) -> str:
    """KST absolute time + Discord relative ('R') marker — e.g. for schedules."""
    return f"{fmt_kst(dt)} ({discord.utils.format_dt(_aware(dt), 'R')})"

# ── Theme ─────────────────────────────────────────────────────────────────

STATUS_COLORS = {
    CTFStatus.UPCOMING: 0x5865F2,   # blurple
    CTFStatus.ACTIVE: 0x57F287,     # green
    CTFStatus.ENDED: 0xFEE75C,     # yellow
    CTFStatus.ARCHIVED: 0x99AAB5,  # grey
}

STATUS_BADGE = {
    CTFStatus.UPCOMING: "\U0001f7e6 UPCOMING",
    CTFStatus.ACTIVE: "\U0001f7e2 LIVE",
    CTFStatus.ENDED: "\U0001f7e1 ENDED",
    CTFStatus.ARCHIVED: "\u26aa ARCHIVED",
}

SEPARATOR = "\u2500" * 30


def _progress_bar(solved: int, total: int, length: int = 10) -> str:
    if total == 0:
        return "\u2591" * length + "  0/0"
    filled = round(solved / total * length)
    bar = "\u2593" * filled + "\u2591" * (length - filled)
    pct = round(solved / total * 100)
    return f"{bar}  {solved}/{total} ({pct}%)"


# ── CTF Embeds ────────────────────────────────────────────────────────────

def ctf_embed(ctf: CTF, member_count: int = 0, challenge_stats: tuple[int, int] | None = None) -> discord.Embed:
    status = ctf.compute_status()
    embed = discord.Embed(
        title=ctf.name,
        description=ctf.description or "",
        color=STATUS_COLORS.get(status, 0x2B2D31),
    )

    # Status badge as first line
    embed.add_field(
        name="\u200b",
        value=f"**{STATUS_BADGE.get(status, 'UNKNOWN')}**",
        inline=False,
    )

    # Time block
    now = datetime.now(timezone.utc)
    start = _aware(ctf.start_time)
    end = _aware(ctf.end_time)

    if status == CTFStatus.UPCOMING:
        time_label = "Starts"
        time_val = discord.utils.format_dt(start, "R")
    elif status == CTFStatus.ACTIVE:
        time_label = "Ends"
        time_val = discord.utils.format_dt(end, "R")
    else:
        time_label = "Ended"
        time_val = discord.utils.format_dt(end, "R")

    embed.add_field(
        name="\U0001f552 Schedule (KST)",
        value=(
            f"**Start:** {fmt_kst(start)}\n"
            f"**End:** {fmt_kst(end)}\n"
            f"**{time_label}:** {time_val}"
        ),
        inline=True,
    )

    # Stats block
    stats_lines = []
    if member_count > 0:
        stats_lines.append(f"\U0001f465 **Members:** {member_count}")
    if challenge_stats:
        solved, total = challenge_stats
        stats_lines.append(f"\U0001f3af **Challenges:** {_progress_bar(solved, total)}")
    if stats_lines:
        embed.add_field(name="\U0001f4ca Stats", value="\n".join(stats_lines), inline=True)

    # Links
    if ctf.ctftime_url:
        embed.add_field(
            name="\U0001f517 Links",
            value=f"[CTFTime]({ctf.ctftime_url})",
            inline=True,
        )

    embed.set_footer(text=f"ID: {ctf.id}  \u2502  /join_ctf {ctf.name}")
    return embed


def ctf_created_embed(ctf: CTF, channels_created: int) -> discord.Embed:
    """Rich embed for the create_ctf response."""
    embed = discord.Embed(
        title="\u2705  CTF Created Successfully",
        color=0x57F287,
    )
    embed.add_field(name="Name", value=f"**{ctf.name}**", inline=True)
    embed.add_field(
        name="Schedule (KST)",
        value=(
            f"{fmt_kst(ctf.start_time)}\n"
            f"\u2192 {fmt_kst(ctf.end_time)}"
        ),
        inline=True,
    )
    embed.add_field(name="Channels", value=f"{channels_created} created", inline=True)
    if ctf.description:
        embed.add_field(name="Description", value=ctf.description, inline=False)
    if ctf.ctftime_url:
        embed.add_field(name="CTFTime", value=ctf.ctftime_url, inline=False)
    embed.add_field(
        name="\u200b",
        value=f"*Users can join with* `/join_ctf {ctf.name}`",
        inline=False,
    )
    embed.set_footer(text=f"CTF ID: {ctf.id}")
    return embed


def ctf_announcement_embed(ctf: CTF, *, member_count: int = 0) -> discord.Embed:
    """Welcome / info embed posted to a CTF's own #announcements channel.

    The Participants field is rendered as a live counter — the bot edits this
    embed in place every time someone joins or leaves the CTF.
    """
    start = _aware(ctf.start_time)
    end = _aware(ctf.end_time)
    embed = discord.Embed(
        title=f"\U0001f3c1  {ctf.name}",
        description=ctf.description or "*No description provided.*",
        color=STATUS_COLORS.get(ctf.compute_status(), 0x5865F2),
    )
    embed.add_field(
        name="\U0001f552 Schedule (KST)",
        value=(
            f"**Start:** {fmt_kst(start)}\n"
            f"**End:** {fmt_kst(end)}\n"
            f"**Starts:** {discord.utils.format_dt(start, 'R')}"
        ),
        inline=False,
    )
    if ctf.ctftime_url:
        embed.add_field(
            name="\U0001f517 Links",
            value=f"[CTFTime]({ctf.ctftime_url})",
            inline=False,
        )
    embed.add_field(
        name="\U0001f465 Participants",
        value=f"**{member_count}** joined  ·  use `/join_ctf` to participate",
        inline=False,
    )
    embed.add_field(
        name="\U0001f4d6 How to use this category",
        value=(
            "• `/add_challenge` — register a new challenge (a dedicated channel is created)\n"
            "• `/solve_challenge` — mark it solved (the channel gets a ✅ prefix)\n"
            "• `/leaderboard` — post the current ranking to #scoreboard\n"
            "• Challenge add/solve activity is logged to **#challenge-log**"
        ),
        inline=False,
    )
    embed.set_footer(text=f"CTF ID: {ctf.id}  │  Good luck, team!")
    return embed


def ctf_list_embed(ctfs: list[CTF]) -> discord.Embed:
    embed = discord.Embed(
        title="\U0001f3c6  CTF List",
        color=0x5865F2,
    )
    if not ctfs:
        embed.description = "*No CTFs found.*"
        return embed

    # Group by status
    groups: dict[str, list[str]] = {"active": [], "upcoming": [], "ended": []}
    for ctf in ctfs:
        status = ctf.compute_status()
        rel = discord.utils.format_dt(_aware(ctf.start_time), "R")
        kst = fmt_kst(ctf.start_time)
        line = f"`{ctf.id:>3}` **{ctf.name}** \u2014 {kst} ({rel})"
        if status == CTFStatus.ACTIVE:
            groups["active"].append(f"\U0001f7e2 {line}")
        elif status == CTFStatus.UPCOMING:
            groups["upcoming"].append(f"\U0001f7e6 {line}")
        else:
            groups["ended"].append(f"\u26aa {line}")

    if groups["active"]:
        embed.add_field(
            name=f"\U0001f525 ACTIVE ({len(groups['active'])})",
            value="\n".join(groups["active"][:10]),
            inline=False,
        )
    if groups["upcoming"]:
        embed.add_field(
            name=f"\U0001f4c5 UPCOMING ({len(groups['upcoming'])})",
            value="\n".join(groups["upcoming"][:10]),
            inline=False,
        )
    if groups["ended"]:
        embed.add_field(
            name=f"\U0001f3c1 ENDED ({len(groups['ended'])})",
            value="\n".join(groups["ended"][:10]),
            inline=False,
        )

    embed.set_footer(text=f"Total: {len(ctfs)} CTFs  \u2502  Use /ctf_info <name> for details")
    return embed


# ── Challenge Embeds ──────────────────────────────────────────────────────

def challenge_added_embed(
    name: str,
    category: str,
    ctf_name: str,
    points: int | None = None,
    added_by: str = "",
    notes: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="\U0001f4cc  New Challenge Added",
        color=0xEB459E,  # fuchsia
    )
    embed.add_field(name="Challenge", value=f"**[{category.upper()}]** {name}", inline=False)
    embed.add_field(name="CTF", value=ctf_name, inline=True)
    if points is not None:
        embed.add_field(name="Points", value=f"`{points}`", inline=True)
    if added_by:
        embed.add_field(name="Added by", value=added_by, inline=True)
    if notes:
        embed.add_field(name="Notes", value=notes, inline=False)
    return embed


def challenge_solved_embed(
    name: str,
    category: str,
    ctf_name: str,
    solver: str,
    points: int | None = None,
    writeup_url: str | None = None,
    notes: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="\U0001f389  Challenge Solved!",
        color=0x57F287,  # green
    )
    embed.add_field(name="Challenge", value=f"**[{category.upper()}]** {name}", inline=False)
    embed.add_field(name="Solved by", value=f"**{solver}**", inline=True)
    embed.add_field(name="CTF", value=ctf_name, inline=True)
    if points is not None:
        embed.add_field(name="Points", value=f"`{points}`", inline=True)
    if writeup_url:
        embed.add_field(name="Writeup", value=f"[Link]({writeup_url})", inline=True)
    if notes:
        embed.add_field(name="Notes", value=notes, inline=False)
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def challenge_list_embed(ctf_name: str, challenges: list, total: int, solved: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"\U0001f3af  Challenges \u2014 {ctf_name}",
        color=0xFEE75C,
    )
    embed.description = f"**Progress:** {_progress_bar(solved, total, 15)}"

    # Group by category
    by_cat: dict[str, list] = {}
    for c in challenges:
        by_cat.setdefault(c.category, []).append(c)

    for cat, challs in sorted(by_cat.items()):
        lines = []
        for c in challs:
            mark = "\u2705" if c.solved else "\u2b1c"
            pts = f" `{c.points}pts`" if c.points else ""
            lines.append(f"{mark} {c.name}{pts}")
        cat_solved = sum(1 for c in challs if c.solved)
        header = f"{cat.upper()} ({cat_solved}/{len(challs)})"
        embed.add_field(name=header, value="\n".join(lines), inline=False)

    return embed


def leaderboard_embed(
    ctf_name: str,
    rows: list[tuple[int, int, "datetime"]],
    *,
    member_count: int = 0,
    achievements: dict | None = None,
    limit: int = 25,
) -> discord.Embed:
    """Render a per-user solve leaderboard for a CTF.

    Each row is ``(user_id, solves, first_solve_at)``. Only per-user solve
    counts are shown — neither "total challenges" nor "total points" appears,
    since participants add their own challenges (and assign their own point
    values), so any comparison against those would be misleading.

    ``achievements`` is the dict returned by ``ctf_service.get_achievements``;
    when present, a small Achievements field is rendered below the ranking.
    """
    embed = discord.Embed(
        title=f"\U0001f3c5  Leaderboard — {ctf_name}",
        color=0xFEE75C,
    )
    if not rows:
        embed.description = "*No solves yet.*"
        embed.set_footer(
            text=(
                f"\U0001f465 Members: {member_count}  │  "
                "Times = when /solve_challenge was used"
            )
        )
        return embed

    medals = {0: "\U0001f947", 1: "\U0001f948", 2: "\U0001f949"}
    lines: list[str] = []
    for idx, (user_id, solves, _first) in enumerate(rows[:limit]):
        rank = medals.get(idx, f"`#{idx + 1:>2}`")
        # Discord renders the mention even if the user is not cached.
        lines.append(f"{rank} <@{user_id}> — **{solves}** solve(s)")

    embed.description = "\n".join(lines)
    if len(rows) > limit:
        embed.description += f"\n\n*…and {len(rows) - limit} more*"

    if achievements:
        ach_lines: list[str] = []
        if achievements.get("first_blood"):
            uid, ts = achievements["first_blood"]
            ach_lines.append(f"\U0001fa78 First Blood — <@{uid}>  ·  {fmt_kst(ts)}")
        if achievements.get("second_blood"):
            uid, ts = achievements["second_blood"]
            ach_lines.append(f"\U0001f948 Second Solve — <@{uid}>  ·  {fmt_kst(ts)}")
        if achievements.get("first_to_milestone"):
            uid, ts = achievements["first_to_milestone"]
            n = achievements.get("milestone", 4)
            ach_lines.append(f"\U0001f3c3 First to {n} solves — <@{uid}>  ·  {fmt_kst(ts)}")
        if ach_lines:
            embed.add_field(
                name="\U0001f396️ Achievements",
                value="\n".join(ach_lines),
                inline=False,
            )

    embed.set_footer(
        text=(
            f"\U0001f465 Members: {member_count}  │  "
            "Times = when /solve_challenge was used"
        )
    )
    return embed


def ctf_end_report_embed(
    ctf: CTF,
    *,
    total_challenges: int,
    solved_count: int,
    by_category: list[tuple[str, int, int]],
    top_solvers: list[tuple[int, int]],
    member_count: int,
) -> discord.Embed:
    """Posted to a CTF's #announcements channel when the scheduler archives it.

    ``by_category`` rows are ``(category, solved, total)``.
    ``top_solvers`` rows are ``(user_id, solves)``.
    """
    embed = discord.Embed(
        title=f"\U0001f3c1  CTF Ended — {ctf.name}",
        description=(
            f"The CTF has ended on **{fmt_kst(ctf.end_time)}**.\n"
            "Channels are now read-only and archived."
        ),
        color=STATUS_COLORS.get(CTFStatus.ENDED, 0xFEE75C),
    )
    embed.add_field(
        name="\U0001f4ca Overall",
        value=_progress_bar(solved_count, total_challenges, 15),
        inline=False,
    )
    if by_category:
        cat_lines = [
            f"• **{cat.upper()}** — {s}/{t}"
            for cat, s, t in sorted(by_category, key=lambda r: r[0])
        ]
        embed.add_field(
            name="\U0001f4c2 Categories", value="\n".join(cat_lines), inline=False
        )
    if top_solvers:
        medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
        lines = [
            f"{medals[i]} <@{uid}> — **{solves}** solve(s)"
            for i, (uid, solves) in enumerate(top_solvers[:3])
        ]
        embed.add_field(name="\U0001f3c6 Top Solvers", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"Members: {member_count}  │  Use /leaderboard for the full ranking")
    return embed


# ── CTFTime Embeds ────────────────────────────────────────────────────────

def ctftime_events_embed(events: list, title: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"\U0001f30d  {title}",
        color=0xED4245,
    )

    if not events:
        embed.description = "*No upcoming events found for this period.*"
        return embed

    lines: list[str] = []
    for i, ev in enumerate(events[:20], 1):
        weight_str = f" \u2502 \u2b50 {ev.weight:.1f}" if ev.weight else ""
        lines.append(
            f"**{i}. [{ev.title}]({ev.ctftime_url})**\n"
            f"\u2003\U0001f552 {fmt_kst(ev.start)} \u2192 {fmt_kst(ev.finish)}\n"
            f"\u2003\U0001f3ae {ev.format}{weight_str}"
        )

    # Split into chunks if too long (embed field limit = 1024)
    text = "\n\n".join(lines)
    if len(text) > 4000:
        mid = len(lines) // 2
        embed.add_field(name="\u200b", value="\n\n".join(lines[:mid]), inline=False)
        embed.add_field(name="\u200b", value="\n\n".join(lines[mid:]), inline=False)
    else:
        embed.description = text

    embed.set_footer(text=f"{len(events)} events  \u2502  Data from ctftime.org")
    return embed


# ── Generic ───────────────────────────────────────────────────────────────

def error_embed(message: str) -> discord.Embed:
    return discord.Embed(
        description=f"\u274c  {message}",
        color=0xED4245,
    )


def success_embed(message: str) -> discord.Embed:
    return discord.Embed(
        description=f"\u2705  {message}",
        color=0x57F287,
    )


def info_embed(title: str, message: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=message,
        color=0x5865F2,
    )
