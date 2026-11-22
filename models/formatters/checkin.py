"""Check-in formatting methods for the Trakt MCP server."""

from models.formatters.utils import format_display_time
from models.types import CheckinResponse


class CheckinFormatters:
    """Helper class for formatting check-in related data for MCP responses."""

    @staticmethod
    def format_checkin_response(response: CheckinResponse) -> str:
        """Format the checkin response from Trakt API.

        Args:
            response: The checkin response data

        Returns:
            Formatted response message
        """
        if response.get("movie"):
            return CheckinFormatters._format_movie_checkin(response)

        try:
            # Extract show and episode info
            show = response.get("show", {})
            episode = response.get("episode", {})

            show_title = show.get("title", "Unknown show")
            episode_title = episode.get("title", "Unknown episode")
            season = episode.get("season", 0)
            number = episode.get("number", 0)

            # Format the success message
            message = "# Successfully Checked In\n\n"
            message += (
                f"You are now checked in to **{show_title}** - "
                f"S{season:02d}E{number:02d}: {episode_title}\n\n"
            )

            # Add watched_at time if available
            if watched_at := response.get("watched_at"):
                watched_time = format_display_time(watched_at)
                message += f"Watched at: {watched_time} UTC\n\n"

            # Add sharing info if available
            if sharing := response.get("sharing", {}):
                platforms: list[str] = []
                for platform, shared in sharing.items():
                    if shared:
                        platforms.append(platform.capitalize())

                if platforms:
                    message += f"Shared on: {', '.join(platforms)}\n\n"

            # Add checkin ID if available
            if checkin_id := response.get("id"):
                message += f"Checkin ID: {checkin_id}\n"

            return message

        except Exception:
            # Fallback for any parsing errors
            return f"Successfully checked in to the show.\n\nDetails: {response!s}"

    @staticmethod
    def _format_movie_checkin(response: CheckinResponse) -> str:
        """Format a movie check-in response."""
        movie = response.get("movie", {})
        title = movie.get("title", "Unknown movie")
        year = movie.get("year")
        label = f"**{title}** ({year})" if year else f"**{title}**"

        message = f"# Successfully Checked In\n\nYou are now checked in to {label}\n\n"

        if watched_at := response.get("watched_at"):
            message += f"Watched at: {format_display_time(watched_at)} UTC\n\n"

        if sharing := response.get("sharing", {}):
            platforms = [
                name.capitalize() for name, shared in sharing.items() if shared
            ]
            if platforms:
                message += f"Shared on: {', '.join(platforms)}\n\n"

        if checkin_id := response.get("id"):
            message += f"Checkin ID: {checkin_id}\n"

        return message

    @staticmethod
    def format_cancel_response() -> str:
        """Format the confirmation for a cancelled check-in."""
        return (
            "# Check-in Cancelled\n\n"
            "Your active check-in was removed. "
            "Any elapsed progress is kept as paused playback, so checking in "
            "to the same item again resumes from it."
        )
