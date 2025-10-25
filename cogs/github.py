import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta
from utils.persistence import save_data
from config import CHECK_INTERVAL_MINUTES

class GitHubCog(commands.Cog):
    """Cog for handling all GitHub-related commands and tasks."""
    
    def __init__(self, bot):
        self.bot = bot
        self.check_issues_loop.start()

    def cog_unload(self):
        """Called when the cog is unloaded."""
        self.check_issues_loop.cancel()


    @commands.command(name='watch', 
                      help='Watch a repo for specific labels, or all new issues.\nUsage: `!watch owner/repo "label one" "label two"`\nTo watch all issues: `!watch owner/repo`')
    async def watch_repo(self, ctx, repo_name: str, *labels: str):
        """Adds a repository to the watch list for the current channel."""
        repo_name = repo_name.strip()
        
        if '/' not in repo_name or len(repo_name.split('/')) != 2:
            await ctx.send(f":x: Invalid format. Please use `owner/repo` (e.g., `!watch microsoft/vscode`)")
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

            valid_labels = [] 
            
            if labels: 
                await loading_msg.edit(content=f":mag: Verifying labels for `{repo_name}`...")
                
                repo_labels_url = f"https://api.github.com/repos/{repo_name}/labels"
                repo_label_names = set()
                page = 1

                # Handle pagination: fetch all labels for the repo
                while True:
                    params = {"page": page, "per_page": 100}
                    async with self.bot.http_session.get(repo_labels_url, params=params) as response:
                        if response.status != 200:
                            await loading_msg.edit(content=f":warning: Could not fetch labels for `{repo_name}`. GitHub API returned status `{response.status}`.")
                            return
                        
                        label_data = await response.json()
                        if not label_data:
                            # No more labels, break the loop
                            break
                        
                        for label in label_data:
                            repo_label_names.add(label['name'].lower()) # Store lowercase for comparison
                        
                        # If we received fewer than 100 labels, this is the last page
                        if len(label_data) < 100:
                            break
                        page += 1

                
                invalid_labels = []
                for user_label in labels:
                    if user_label.lower() not in repo_label_names:
                        invalid_labels.append(f"`{user_label}`")
                    else:
                        # Store the original casing for future use
                        valid_labels.append(user_label) 

                if invalid_labels:
                    invalid_str = ", ".join(invalid_labels)
                    await loading_msg.edit(content=f":x: Error: Repository `{repo_name}` found, but the following labels do not exist: {invalid_str}")
                    return
                
                if not valid_labels:
                    await loading_msg.edit(content=f":x: Error: No valid labels were provided, but you specified some.")
                    return
            
            

            channel_id = ctx.channel.id
            
            start_time_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            
            self.bot.watched_repos[repo_name] = {
                "channel_id": channel_id,
                "labels": valid_labels, 
                "watch_since_time": start_time_iso
            }
            
            save_data(self.bot.watched_repos, self.bot.notified_issues)
            
            # --- MODIFIED SUCCESS MESSAGE ---
            if valid_labels:
                label_str = ", ".join([f"`{l}`" for l in valid_labels])
                await loading_msg.edit(content=f":white_check_mark: Now watching `{repo_name}` for labels: {label_str}. \nNotifications will be sent to this channel.")
            else:
                await loading_msg.edit(content=f":white_check_mark: Now watching `{repo_name}` for **all new issues**. \nNotifications will be sent to this channel.")

        except aiohttp.ClientError as e:
            print(f"Network error during repo verification: {e}")
            await loading_msg.edit(content=f":warning: A network error occurred while trying to verify the repository.")
        except Exception as e:
            print(f"Unexpected error in !watch: {e}")
            await loading_msg.edit(content=f":warning: An unexpected error occurred.")
            raise e 

    @watch_repo.error
    async def watch_repo_error(self, ctx, error):
        """Error handler for the !watch command."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'repo_name':
                await ctx.send(f":warning: You forgot the repository name! \nUsage: `!watch owner/repo \"label one\"`")
        else:
            await ctx.send(f":x: An error occurred: {error}")
            raise error 

    @commands.command(name='unwatch', 
                      help='Stop watching a repository.\nUsage: `!unwatch owner/repo`')
    async def unwatch_repo(self, ctx, repo_name: str):
        """Removes a repository from the watch list."""
        repo_name = repo_name.strip()
        
        if repo_name in self.bot.watched_repos:
            del self.bot.watched_repos[repo_name]
            save_data(self.bot.watched_repos, self.bot.notified_issues)
            await ctx.send(f":x: Stopped watching `{repo_name}`.")
        else:
            await ctx.send(f":grey_question: I am not currently watching `{repo_name}`.")

    @unwatch_repo.error
    async def unwatch_repo_error(self, ctx, error):
        """Error handler for the !unwatch command."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'repo_name':
                await ctx.send(f":warning: You forgot the repository name! \nUsage: `!unwatch owner/repo`")
        else:
            await ctx.send(f":x: An error occurred: {error}")
            raise error 
    @commands.command(name='list', 
                      help='Show all repositories being watched in this server.')
    async def list_watched(self, ctx):
        """Lists all repositories and their notification channels."""
        if not self.bot.watched_repos:
            await ctx.send("I am not watching any repositories.")
            return
        
        embed = discord.Embed(title="Watched Repositories", color=discord.Color.blue())
        
        description = ""
        count = 0
        # Only show repos being watched in this guild (server)
        for repo, data in self.bot.watched_repos.items():
            channel = self.bot.get_channel(data['channel_id'])
            # Check if channel is in the same server this command was run
            if channel and channel.guild == ctx.guild:
                count += 1
                channel_id = data['channel_id']
                labels = data['labels']
                channel_name = f"<#{channel_id}>"
                
                # --- MODIFIED LABEL STRING ---
                if labels:
                    label_str = ", ".join([f"`{l}`" for l in labels])
                else:
                    label_str = "**All new issues**"
                # --- END MODIFIED ---
                
                # Try to get a formatted time string
                time_str = " (Time not set)"
                if data.get('watch_since_time'):
                    try:
                        time_dt = datetime.fromisoformat(data['watch_since_time'].replace('Z', '+00:00'))
                        # Format as relative time for Discord <t:TIMESTAMP:R>
                        time_str = f" (since <t:{int(time_dt.timestamp())}:R>)"
                    except:
                        pass # Keep default time_str

                description += f"**`{repo}`**{time_str}\n<:arrow_right:1234567890> Channel: {channel_name}\n<:arrow_right:1234567890> Labels: {label_str}\n\n"
        
        if count == 0:
            await ctx.send("I am not watching any repositories in this server.")
            return

        # Replace the placeholder emoji with a real one (or remove)
        embed.description = description.replace("<:arrow_right:1234567890>", "•")
        await ctx.send(embed=embed)

    # --- BACKGROUND TASK ---

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_issues_loop(self):
        """The main background loop that checks GitHub for new issues."""
        # Record the time *before* we start the check
        current_run_time_utc = datetime.now(timezone.utc)
        print(f"[{datetime.now()}] Running GitHub check...")
        
        if not self.bot.watched_repos:
            print("No repos to watch. Skipping check.")
            return

        # Base parameters: get issues sorted by last update, newest first
        base_params = {"state": "open", "sort": "updated", "direction": "desc"}
        
        current_notified_issues = set(self.bot.notified_issues)
        repos_to_remove = []
        
        # Flag to see if we need to save data (because we updated a since_time)
        data_was_modified = False

        for repo, data in list(self.bot.watched_repos.items()):
            channel_id = data['channel_id']
            labels = data['labels']
            
            
            # --- MODIFIED ---
            # Create a copy of the base params
            params = base_params.copy()
            
            # Only add the 'labels' parameter if we are watching for specific labels
            if labels:
                params["labels"] = ",".join(labels)
            # --- END MODIFIED ---
            
            # Get the *per-repo* start time
            repo_since_time = data.get('watch_since_time')
            
            if repo_since_time:
                # Use a 1-second buffer to avoid race conditions
                try:
                    since_dt = datetime.fromisoformat(repo_since_time.replace('Z', '+00:00'))
                    since_dt_buffered = since_dt - timedelta(seconds=1)
                    params["since"] = since_dt_buffered.isoformat().replace('+00:00', 'Z')
                except ValueError:
                    print(f"  - Error: Invalid time format for {repo}: {repo_since_time}. Fetching all.")
                    # Fallback: Don't use 'since' this time if format is bad
            else:
                # This is an old entry from before we tracked time.
                # We'll fetch all, and `notified_issues` will prevent spam.
                # We will set the time for next run below.
                print(f"  - No 'watch_since_time' for {repo}. Fetching all and setting time for next run.")
                data_was_modified = True # Mark to save the new time
            # -----------------
            
            url = f"https://api.github.com/repos/{repo}/issues"
            
            # --- MODIFIED LOGGING ---
            if labels:
                print(f"  - Checking {repo} for labels: {params['labels']}")
            else:
                print(f"  - Checking {repo} for **all new issues**")
            # --- END MODIFIED ---
                
            if 'since' in params:
                print(f"  - Checking for issues updated since: {params['since']}")
            
            try:
                # Use the new `params`
                async with self.bot.http_session.get(url, params=params) as response:
                    
                    if response.status == 200:
                        issues = await response.json()
                        if not issues:
                            print(f"  - No matching issues found for {repo}.")
                            continue
                        
                        print(f"  - Found {len(issues)} matching issues for {repo}.")
                        
                        for issue in issues:
                            issue_id = f"{repo}#{issue['number']}"
                            
                            # We also need to check if the issue was *created* after the watch time
                            # The 'since' param is for 'updated', so an old issue just getting a
                            # new label would appear. We only want *new* issues.
                            
                            issue_created_at = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
                            
                            # --- MODIFIED WATCH_STARTED_AT LOGIC ---
                            # It's possible repo_since_time is None if it's an old entry
                            # In that case, we can't compare, so we just use the notified_issues set
                            watch_started_at = None
                            if repo_since_time:
                                try:
                                    watch_started_at = datetime.fromisoformat(repo_since_time.replace('Z', '+00:00'))
                                except ValueError:
                                    pass # watch_started_at remains None
                            
                            # Check if issue is new
                            passes_newness_check = issue_id not in self.bot.notified_issues
                            
                            # Check if issue was created *after* we started watching
                            # If we don't have a start time, we'll just rely on the newness_check
                            passes_time_check = True # Default to true
                            if watch_started_at:
                                passes_time_check = (issue_created_at >= watch_started_at)
                            else:
                                print(f"    - No watch_started_at for {issue_id}, relying on notified_issues set.")

                            if passes_newness_check and passes_time_check:
                            # --- END MODIFIED ---
                                print(f"    - NEW Issue Found: {issue_id}")
                                current_notified_issues.add(issue_id)
                                
                                channel = self.bot.get_channel(channel_id)
                                if channel:
                                    await self.send_notification(channel, repo, issue, labels)
                                else:
                                    print(f"    - Error: Channel {channel_id} not found for repo {repo}.")
                            elif issue_id in self.bot.notified_issues:
                                print(f"    - Ignoring already notified issue: {issue_id}")
                            else:
                                # This else now catches issues that failed the time check
                                if watch_started_at:
                                    print(f"    - Ignoring old issue: {issue_id} (created {issue_created_at}, watching since {watch_started_at})")
                                else:
                                    print(f"    - Ignoring old issue: {issue_id} (created {issue_created_at}, no watch time set)")

                    
                    elif response.status == 404:
                        print(f"  - Error: Repository {repo} not found (404).")
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(f":warning: Repository `{repo}` could not be found. It may have been deleted or renamed. Removing from watch list.")
                        repos_to_remove.append(repo)

                    else:
                        print(f"  - Error: GitHub API returned {response.status} for {repo}.")
                        
            except aiohttp.ClientError as e:
                print(f"  - Error: Network or client error checking {repo}: {e}")
            
            if self.bot.watched_repos.get(repo): # Check if it wasn't deleted
                self.bot.watched_repos[repo]['watch_since_time'] = current_run_time_utc.isoformat().replace('+00:00', 'Z')
                data_was_modified = True
            # --- END NEW ---
            
            await asyncio.sleep(2) 

        for repo in repos_to_remove:
            if repo in self.bot.watched_repos:
                del self.bot.watched_repos[repo]
                data_was_modified = True # We changed the data
                
        self.bot.notified_issues.update(current_notified_issues)
        
        # Only save if we actually need to
        if data_was_modified:
            save_data(self.bot.watched_repos, self.bot.notified_issues)
        
        print("GitHub check finished.")


    async def send_notification(self, channel, repo, issue, watched_labels):
        """Formats and sends a single issue notification to a channel."""
        
        embed = discord.Embed(
            title=f"New Issue in `{repo}`", # Changed title
            description=issue['title'],
            url=issue['html_url'],
            color=discord.Color.green(),
            timestamp=datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
        )
        
        embed.add_field(name="Issue Number", value=f"#{issue['number']}", inline=True)
        embed.add_field(name="Created By", value=f"[{issue['user']['login']}]({issue['user']['html_url']})", inline=True)
        
        issue_labels = [label['name'] for label in issue['labels']]
        
        # Only highlight labels if we are watching for specific ones
        if watched_labels:
            embed.title = f"New Matching Issue in `{repo}`" # Revert to old title
            watched_label_set_lower = set(l.lower() for l in watched_labels)
            
            formatted_labels = []
            for name in issue_labels:
                if name.lower() in watched_label_set_lower:
                    formatted_labels.append(f"**`{name}`** :star:") # Highlights the label that matched
                else:
                    formatted_labels.append(f"`{name}`")
            
            if formatted_labels:
                embed.add_field(name="Labels", value=', '.join(formatted_labels), inline=False)
        
        elif issue_labels:
            # If we're watching ALL issues, just list the labels without highlighting
            formatted_labels = [f"`{name}`" for name in issue_labels]
            embed.add_field(name="Labels", value=', '.join(formatted_labels), inline=False)
            
        embed.set_footer(text=f"Repo: {repo}")
        
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            print(f"Error: Bot does not have permission to send messages in channel {channel.id} ({channel.name}).")
        except Exception as e:
            print(f"Error sending message: {e}")

    @check_issues_loop.before_loop
    async def before_check_loop(self):
        """Waits for the bot to be logged in before starting the loop."""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GitHubCog(bot))

