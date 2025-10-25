import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    """A custom help command that looks much nicer."""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='help', help='Shows this help message.')
    async def help(self, ctx, *, command_name: str = None):
        """Shows help for all commands, or a specific command."""
        
        prefix = self.bot.command_prefix
        
        if command_name is None:
            # --- Show help for ALL commands ---
            embed = discord.Embed(
                title="GitHub Issue Notifier Help",
                description=f"Here are all the commands you can use. \nType `{prefix}help [command]` for more info on a command.",
                color=discord.Color.blurple()
            )
            
            # Find commands from all cogs
            for cog_name, cog in self.bot.cogs.items():
                # Get commands from the cog, skipping hidden ones
                cog_commands = [c for c in cog.get_commands() if not c.hidden]
                if not cog_commands:
                    continue
                    
                command_list = []
                for command in cog_commands:
                    # Use the short_doc or the first line of the help string
                    short_help = command.help.split('\n')[0]
                    command_list.append(f"`{prefix}{command.name}` - {short_help}")
                
                embed.add_field(
                    name=f"{cog_name} Commands", 
                    value="\n".join(command_list), 
                    inline=False
                )
                
            embed.set_footer(text="Made with discord.py")
            await ctx.send(embed=embed)
            
        else:
            # --- Show help for a SPECIFIC command ---
            command = self.bot.get_command(command_name)
            
            if command is None or command.hidden:
                await ctx.send(f":x: No command named `{command_name}` found.")
                return

            # Create an embed for the specific command
            embed = discord.Embed(
                title=f"Help: `{prefix}{command.name}`",
                description=command.help or "No description available.", # Use the full help string
                color=discord.Color.green()
            )
            
            # Add aliases if they exist
            if command.aliases:
                aliases = ", ".join([f"`{a}`" for a in command.aliases])
                embed.add_field(name="Aliases", value=aliases, inline=False)
                
            embed.set_footer(text=f"Usage: {prefix}{command.name} {command.signature}")
            await ctx.send(embed=embed)


# This function is required by discord.py to load the cog
async def setup(bot):
    await bot.add_cog(HelpCog(bot))
