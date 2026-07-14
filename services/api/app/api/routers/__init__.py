"""Router registry for the FastAPI application."""

from app.api.routers import (
    analysis,
    auth,
    champions,
    chat,
    live_game,
    matches,
    ops,
    rank,
    reset,
    search,
    users,
)

all_routers = [
    auth.router,
    users.router,
    matches.router,
    search.router,
    champions.router,
    rank.router,
    reset.router,
    ops.router,
    live_game.router,
    analysis.router,
    chat.router,
]
