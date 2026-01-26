"""Router registry for the FastAPI application."""

from app.api.routers import auth, champions, matches, reset, users

all_routers = [
    auth.router,
    users.router,
    matches.router,
    champions.router,
    reset.router,
]
