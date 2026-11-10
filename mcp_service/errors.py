"""Errors whose message is meant to be read by Claude (and shown to the shopper)."""


class ToolUserError(Exception):
    """The request cannot be answered as asked; the message says why and what to do instead."""


class ApiBusy(ToolUserError):
    """The API did not answer in time, was unreachable, or answered 503."""

    def __init__(self) -> None:
        super().__init__("השירות עמוס, נסה שוב בעוד רגע")
