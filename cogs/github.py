from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import aiohttp
import discord
from discord.ext import commands, tasks

from config import CHECK_INTERVAL_MINUTES
from utils.persistence import save_data

logger = logging.getLogger(__name__)

DEFAULT_WATCH_TYPE = "issues"
POSSIBLE_WATCH_TYPES = ("issues", "prs", "all")
RATE_LIMIT_WARN_THRESHOLD = 5
ISSUES_PER_PAGE = 100

WATCH_TYPE_LABELS = {
    "issues": "issues",
    "prs": "pull requests",
    "all": "issues and pull requests",
}
WATCH_TYPE_LIST_LABELS = {
    "issues": "Issues Only",
    "prs": "PRs Only",
    "all": "Issues & PRs",
}


class WatchArgsError(ValueError):
    """Raised when !watch's variadic arguments can't be parsed."""


def parse_watch_args(args: tuple[str, ...]) -> tuple[list[str], str]:
    """Parses the label/--type arguments accepted by !watch.

    Returns (labels, watch_type). Raises WatchArgsError with a
    user-facing message if --type is given an invalid value.
    """
    labels: list[str] = []
    watch_type = DEFAULT_WATCH_TYPE

    i = 0
    while i < len(args):
        arg = args[i]
        if arg.lower() == "--type":
            if i + 1 < len(args) and args[i + 1].lower() in POSSIBLE_WATCH_TYPES:
                watch_type = args[i + 1].lower()
                i += 2
                continue
            raise WatchArgsError(
                "Invalid value for `--type`. Must be `issues`, `prs`, or `all`."
            )
        labels.append(arg)
        i += 1

    return labels, watch_type


def matches_labels(item_labels: list[str], watched_labels: list[str]) -> bool:
    """True if no specific labels are being watched (i.e. watch all),
    or if any watched label matches one of the item's labels (case-insensitive)."""
    if not watched_labels:
        return True
    item_label_set = {name.lower() for name in item_labels}
    return any(label.lower() in item_label_set for label in watched_labels)


def should_notify_item(
    *,
    is_pr: bool,
    watch_type: str,
    item_labels: list[str],
    watched_labels: list[str],
    notified_key: str,
    notified_issues: set[str],
    issue_created_at: datetime,
    watch_since_time: Optional[datetime],
) -> bool:
    """Decides whether a single channel-watch should be notified about a
    single GitHub issue/PR item."""
    if watch_type == "issues" and is_pr:
        return False
    if watch_type == "prs" and not is_pr:
        return False
    if not matches_labels(item_labels, watched_labels):
        return False
    if notified_key in notified_issues:
        return False
    if watch_since_time is not None and issue_created_at < watch_since_time:
        return False
    return True


def _parse_iso(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


class GitHubCog(commands.Cog):
    """Cog for handling all GitHub-related commands and tasks."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_issues_loop.start()

    def cog_unload(self):
        """Called when the cog is unloaded."""
        self.check_issues_loop.cancel()

    @commands.command(name='watch',
                      help='Watch a repo for issues, pull requests, or both.\n'
                           'Usage: `!watch owner/repo [labels...] [--type <type>]`\n'
                           'Types: `issues` (default), `prs`, `all`\n'
                           'Requires the "Manage Server" permission.\n'
                           'Example: `!watch owner/repo "help wanted" --type all`\n'
                           'Example: `!watch owner/repo --type prs`')
    @commands.has_permissions(manage_guild=True)
    async def watch_repo(self, ctx: commands.Context, repo_name: str, *args: str):
        """Adds a repository to the watch list for the current channel."""
        repo_name = repo_name.strip()

        if '/' not in repo_name or len(repo_name.split('/')) != 2:
            await ctx.send(":x: Invalid format. Please use `owner/repo` (e.g., `!watch microsoft/vscode`)")
            return

        try:
            labels, watch_type = parse_watch_args(args)
        except WatchArgsError as e:
            await ctx.send(f":x: {e}")
            return

        loading_msg = await ctx.send(f":mag: Verifying repository `{repo_name}`...")

        try:
            repo_url = f"https://api.github.com/repos/{repo_name}"
            async with self.bot.http_session.get(repo_url) as response:
                if response.status == 404:
                    await loading_msg.edit(content=f":x: Error: Repository `{repo_name}` not found. Please check the spelling.")
                    return
                elif response.status != 200:
                    await loading_msg.edit(content=f":warning: Could not verify repository. GitHub API returned status `{response.status}`.")
                    return

            valid_labels: list[str] = []

            if labels:
                await loading_msg.edit(content=f":mag: Verifying labels for `{repo_name}`...")

                repo_labels_url = f"https://api.github.com/repos/{repo_name}/labels"
                repo_label_names: set[str] = set()
                page = 1

                while True:
                    params = {"page": page, "per_page": 100}
                    async with self.bot.http_session.get(repo_labels_url, params=params) as response:
                        if response.status != 200:
                            await loading_msg.edit(content=f":warning: Could not fetch labels for `{repo_name}`. GitHub API returned status `{response.status}`.")
                            return

                        label_data = await response.json()
                        if not label_data:
                            break

                        for label in label_data:
                            repo_label_names.add(label['name'].lower())

                        if len(label_data) < 100:
                            break
                        page += 1

                invalid_labels = []
                for user_label in labels:
                    if user_label.lower() not in repo_label_names:
                        invalid_labels.append(f"`{user_label}`")
                    else:
                        valid_labels.append(user_label)

                if invalid_labels:
                    invalid_str = ", ".join(invalid_labels)
                    await loading_msg.edit(content=f":x: Error: Repository `{repo_name}` found, but the following labels do not exist: {invalid_str}")
                    return

                if not valid_labels:
                    await loading_msg.edit(content=":x: Error: No valid labels were provided, but you specified some.")
                    return

            # All checks passed, save the data for this channel only -
            # other channels already watching this repo are untouched.
            channel_id = str(ctx.channel.id)
            start_time_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

            repo_channels = self.bot.watched_repos.setdefault(repo_name, {})
            repo_channels[channel_id] = {
                "labels": valid_labels,
                "watch_since_time": start_time_iso,
                "watch_type": watch_type,
            }

            save_data(self.bot.watched_repos, self.bot.notified_issues)

            type_str = WATCH_TYPE_LABELS[watch_type]

            if valid_labels:
                label_str = ", ".join([f"`{l}`" for l in valid_labels])
                await loading_msg.edit(content=f":white_check_mark: Now watching `{repo_name}` for new **{type_str}** with labels: {label_str}. \nNotifications will be sent to this channel.")
            else:
                await loading_msg.edit(content=f":white_check_mark: Now watching `{repo_name}` for **all new {type_str}**. \nNotifications will be sent to this channel.")

        except aiohttp.ClientError as e:
            logger.warning("Network error during repo verification: %s", e)
            await loading_msg.edit(content=":warning: A network error occurred while trying to verify the repository.")
        except Exception as e:
            logger.exception("Unexpected error in !watch")
            await loading_msg.edit(content=":warning: An unexpected error occurred.")
            raise e

    @watch_repo.error
    async def watch_repo_error(self, ctx: commands.Context, error: commands.CommandError):
        """Error handler for the !watch command."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'repo_name':
                await ctx.send(":warning: You forgot the repository name! \nUsage: `!watch owner/repo \"label one\"`")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(":no_entry_sign: You don't have permission to use that command. (Requires: Manage Server)")
        else:
            await ctx.send(f":x: An error occurred: {error}")
            raise error

    @commands.command(name='unwatch',
                      help='Stop watching a repository in this channel.\n'
                           'Usage: `!unwatch owner/repo`\n'
                           'Requires the "Manage Server" permission.')
    @commands.has_permissions(manage_guild=True)
    async def unwatch_repo(self, ctx: commands.Context, repo_name: str):
        """Removes a repository from the watch list for the current channel."""
        repo_name = repo_name.strip()
        channel_id = str(ctx.channel.id)

        repo_channels = self.bot.watched_repos.get(repo_name)
        if not repo_channels or channel_id not in repo_channels:
            await ctx.send(f":grey_question: I am not currently watching `{repo_name}` in this channel.")
            return

        del repo_channels[channel_id]
        if not repo_channels:
            del self.bot.watched_repos[repo_name]

        # Bound the growth of notified_issues by dropping entries for this
        # channel+repo now that it's no longer being watched.
        stale_prefix = f"{channel_id}:{repo_name}#"
        self.bot.notified_issues = {
            entry for entry in self.bot.notified_issues if not entry.startswith(stale_prefix)
        }

        save_data(self.bot.watched_repos, self.bot.notified_issues)
        await ctx.send(f":x: Stopped watching `{repo_name}` in this channel.")

    @unwatch_repo.error
    async def unwatch_repo_error(self, ctx: commands.Context, error: commands.CommandError):
        """Error handler for the !unwatch command."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'repo_name':
                await ctx.send(":warning: You forgot the repository name! \nUsage: `!unwatch owner/repo`")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(":no_entry_sign: You don't have permission to use that command. (Requires: Manage Server)")
        else:
            await ctx.send(f":x: An error occurred: {error}")
            raise error

    @commands.command(name='list',
                      help='Show all repositories being watched in this server.')
    async def list_watched(self, ctx: commands.Context):
        """Lists all repositories and their notification channels."""
        if not self.bot.watched_repos:
            await ctx.send("I am not watching any repositories.")
            return

        embed = discord.Embed(title="Watched Repositories", color=discord.Color.blue())

        description = ""
        count = 0
        for repo, channels in self.bot.watched_repos.items():
            for channel_id_str, data in channels.items():
                channel = self.bot.get_channel(int(channel_id_str))
                if not channel or channel.guild != ctx.guild:
                    continue

                count += 1
                labels = data.get('labels', [])
                watch_type = data.get("watch_type", DEFAULT_WATCH_TYPE)
                channel_name = f"<#{channel_id_str}>"

                if labels:
                    label_str = ", ".join([f"`{l}`" for l in labels])
                else:
                    label_str = "**All**"

                time_str = " (Time not set)"
                since_dt = _parse_iso(data.get('watch_since_time'))
                if since_dt:
                    time_str = f" (since <t:{int(since_dt.timestamp())}:R>)"

                type_str = WATCH_TYPE_LIST_LABELS[watch_type]

                description += (f"**`{repo}`**{time_str}\n"
                              f"• Channel: {channel_name}\n"
                              f"• Type: **{type_str}**\n"
                              f"• Labels: {label_str}\n\n")

        if count == 0:
            await ctx.send("I am not watching any repositories in this server.")
            return

        embed.description = description
        await ctx.send(embed=embed)

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_issues_loop(self):
        """The main background loop that checks GitHub for new issues."""

        current_run_time_utc = datetime.now(timezone.utc)
        logger.info("Running GitHub check...")

        if not self.bot.watched_repos:
            logger.info("No repos to watch. Skipping check.")
            return

        notified_issues = self.bot.notified_issues
        repos_to_remove: list[str] = []
        data_was_modified = False
        rate_limited = False

        for repo, channels in list(self.bot.watched_repos.items()):
            if rate_limited:
                logger.warning("Stopping this cycle early due to GitHub rate limit.")
                break

            if not channels:
                continue

            since_dt_min: Optional[datetime] = None
            for data in channels.values():
                dt = _parse_iso(data.get('watch_since_time'))
                if dt and (since_dt_min is None or dt < since_dt_min):
                    since_dt_min = dt

            params: dict[str, Any] = {
                "state": "open",
                "sort": "updated",
                "direction": "desc",
                "per_page": ISSUES_PER_PAGE,
            }
            if since_dt_min:
                since_buffered = since_dt_min - timedelta(seconds=1)
                params["since"] = since_buffered.isoformat().replace('+00:00', 'Z')

            url = f"https://api.github.com/repos/{repo}/issues"
            logger.info("Checking %s (%d channel(s) watching)%s", repo, len(channels),
                        f", since {params['since']}" if 'since' in params else "")

            items: list[dict] = []
            repo_missing = False
            rate_limited_mid_repo = False
            page = 1

            try:
                while True:
                    page_params = {**params, "page": page}
                    async with self.bot.http_session.get(url, params=page_params) as response:
                        remaining = response.headers.get("X-RateLimit-Remaining")

                        if response.status == 200:
                            page_items = await response.json()
                            items.extend(page_items)
                            got_full_page = len(page_items) == ISSUES_PER_PAGE
                        elif response.status == 404:
                            logger.warning("Repository %s not found (404).", repo)
                            repo_missing = True
                            break
                        else:
                            logger.warning("GitHub API returned %d for %s.", response.status, repo)
                            break

                        if remaining is not None:
                            try:
                                if int(remaining) <= RATE_LIMIT_WARN_THRESHOLD:
                                    logger.warning(
                                        "GitHub rate limit nearly exhausted (%s remaining). "
                                        "Pausing checks until next cycle.", remaining,
                                    )
                                    rate_limited = True
                                    rate_limited_mid_repo = True
                                    break
                            except ValueError:
                                pass

                        if not got_full_page:
                            break
                        page += 1
            except aiohttp.ClientError as e:
                logger.warning("Network or client error checking %s: %s", repo, e)
                continue

            if repo_missing:
                for channel_id_str in channels:
                    channel = self.bot.get_channel(int(channel_id_str))
                    if channel:
                        await channel.send(f":warning: Repository `{repo}` could not be found. It may have been deleted or renamed. Removing from watch list.")
                repos_to_remove.append(repo)
                continue

            if not items:
                logger.info("No matching items found for %s.", repo)
            else:
                logger.info("Found %d items for %s.", len(items), repo)
                for item in items:
                    is_pr = 'pull_request' in item
                    issue_created_at = _parse_iso(item['created_at'])
                    repo_issue_id = f"{repo}#{item['number']}"
                    item_labels = [label['name'] for label in item['labels']]

                    for channel_id_str, data in channels.items():
                        watch_type = data.get("watch_type", DEFAULT_WATCH_TYPE)
                        watched_labels = data.get("labels", [])
                        watch_since_dt = _parse_iso(data.get('watch_since_time'))
                        notified_key = f"{channel_id_str}:{repo_issue_id}"

                        if should_notify_item(
                            is_pr=is_pr,
                            watch_type=watch_type,
                            item_labels=item_labels,
                            watched_labels=watched_labels,
                            notified_key=notified_key,
                            notified_issues=notified_issues,
                            issue_created_at=issue_created_at,
                            watch_since_time=watch_since_dt,
                        ):
                            logger.info("NEW item found: %s for channel %s", notified_key, channel_id_str)
                            notified_issues.add(notified_key)

                            channel = self.bot.get_channel(int(channel_id_str))
                            if channel:
                                await self.send_notification(channel, repo, item, watched_labels, is_pr)
                            else:
                                logger.warning("Channel %s not found for repo %s.", channel_id_str, repo)

            # Advance each channel's since-time to when this run started -
            # but only if we weren't cut short by the rate limit, otherwise
            # we'd skip items on unfetched pages next time.
            if not rate_limited_mid_repo:
                for data in channels.values():
                    data["watch_since_time"] = current_run_time_utc.isoformat().replace('+00:00', 'Z')
                data_was_modified = True

            await asyncio.sleep(2)

        for repo in repos_to_remove:
            if self.bot.watched_repos.pop(repo, None) is not None:
                data_was_modified = True

        if data_was_modified:
            save_data(self.bot.watched_repos, self.bot.notified_issues)

        logger.info("GitHub check finished.")

    async def send_notification(self, channel: discord.abc.Messageable, repo: str, issue: dict, watched_labels: list[str], is_pr: bool):
        """Formats and sends a single issue notification to a channel."""

        item_type_str = "New Pull Request" if is_pr else "New Issue"
        color = discord.Color.blue() if is_pr else discord.Color.green()

        embed = discord.Embed(
            title=item_type_str,
            description=issue['title'],
            url=issue['html_url'],
            color=color,
            timestamp=_parse_iso(issue['created_at']),
        )

        embed.add_field(name="Repository", value=f"`{repo}`", inline=False)

        item_type_field_name = "PR Number" if is_pr else "Issue Number"
        embed.add_field(name=item_type_field_name, value=f"#{issue['number']}", inline=True)

        embed.add_field(name="Created By", value=f"[{issue['user']['login']}]({issue['user']['html_url']})", inline=True)

        issue_labels = [label['name'] for label in issue['labels']]

        if watched_labels:
            watched_label_set_lower = {l.lower() for l in watched_labels}

            formatted_labels = []
            for name in issue_labels:
                if name.lower() in watched_label_set_lower:
                    formatted_labels.append(f"**`{name}`** :star:")
                else:
                    formatted_labels.append(f"`{name}`")

            if formatted_labels:
                embed.add_field(name="Labels", value=', '.join(formatted_labels), inline=False)

        elif issue_labels:
            formatted_labels = [f"`{name}`" for name in issue_labels]
            embed.add_field(name="Labels", value=', '.join(formatted_labels), inline=False)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Bot does not have permission to send messages in channel %s (%s).", channel.id, getattr(channel, 'name', '?'))
        except Exception:
            logger.exception("Error sending message")

    @check_issues_loop.before_loop
    async def before_check_loop(self):
        """Waits for the bot to be logged in before starting the loop."""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    """Required setup function to load the cog."""
    await bot.add_cog(GitHubCog(bot))
