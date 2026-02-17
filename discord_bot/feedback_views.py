import discord
from discord import ui
from src.functions import groq_utils, discord_utils


class FeedbackModal(ui.Modal, title="Session Feedback"):
    """Modal for entering session feedback."""

    feedback_input = ui.TextInput(
        label="How did the session go?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe what was covered and how the student performed...",
        required=True,
        max_length=250,
    )

    def __init__(self, session_id: str, student_name: str, tutor_name: str, session_time: str, original_message: discord.Message):
        super().__init__()
        self.session_id = session_id
        self.student_name = student_name
        self.tutor_name = tutor_name
        self.session_time = session_time
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        raw_feedback = self.feedback_input.value

        # Generate AI summary
        summary = groq_utils.generate_feedback_summary(raw_feedback, self.student_name)

        if not summary:
            await interaction.followup.send(
                "Failed to generate summary. Please try again.",
                ephemeral=True
            )
            return

        # Post to feedback channel
        success = discord_utils.post_feedback_to_channel(
            student_name=self.student_name,
            tutor_name=self.tutor_name,
            session_time=self.session_time,
            summary=summary
        )

        if success:
            # Update the original message to show feedback was submitted
            try:
                # Create updated embed
                completed_embed = discord.Embed(
                    title="✅ Feedback Submitted",
                    description=f"Thank you for providing feedback for **{self.student_name}**'s session.",
                    color=discord.Color.green()
                )
                completed_embed.add_field(name="Student", value=self.student_name, inline=True)
                completed_embed.add_field(name="Time", value=self.session_time, inline=True)

                # Edit message to remove button and update embed
                await self.original_message.edit(embed=completed_embed, view=None)
            except Exception:
                pass  # If edit fails, continue anyway

            await interaction.followup.send(
                "Feedback submitted successfully! ✅",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Failed to post feedback. Please try again. ❌",
                ephemeral=True
            )


class FeedbackButton(ui.View):
    """Persistent view with feedback button."""

    def __init__(self):
        # timeout=None makes this a persistent view
        super().__init__(timeout=None)

    @ui.button(
        label="Leave Feedback",
        style=discord.ButtonStyle.primary,
        custom_id="feedback_button",
        emoji="📝"
    )
    async def feedback_button(self, interaction: discord.Interaction, button: ui.Button):
        # Parse session info from the message embed
        embed = interaction.message.embeds[0] if interaction.message.embeds else None

        if not embed:
            await interaction.response.send_message("Could not find session info.", ephemeral=True)
            return

        # Check if feedback was already submitted
        if embed.title and "Feedback Submitted" in embed.title:
            await interaction.response.send_message("Feedback has already been submitted for this session.", ephemeral=True)
            return

        # Extract info from embed fields
        session_id = None
        student_name = None
        tutor_name = None
        session_time = None

        for field in embed.fields:
            if field.name == "Session ID":
                session_id = field.value
            elif field.name == "Student":
                student_name = field.value
            elif field.name == "Tutor":
                tutor_name = field.value
            elif field.name == "Time":
                session_time = field.value

        if not all([session_id, student_name, tutor_name, session_time]):
            await interaction.response.send_message("Missing session information.", ephemeral=True)
            return

        modal = FeedbackModal(session_id, student_name, tutor_name, session_time, interaction.message)
        await interaction.response.send_modal(modal)
