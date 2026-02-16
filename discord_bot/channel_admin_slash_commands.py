from discord.ext import commands
from tutor_slash_commands import TutorCommands


class ChannelAdminCommands(TutorCommands):
    """Commands for channel admins. Inherits all tutor commands."""

    CHANNEL_ADMIN_COMMANDS = {
        "list_students": "List all students for a tutor",
        "tutor_info": "View tutor details for this channel",
    }

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        pass
