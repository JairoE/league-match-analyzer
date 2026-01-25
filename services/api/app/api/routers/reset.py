from fastapi import APIRouter, status

from app.core.logging import get_logger
from app.schemas.reset import ResetResult
from app.services.champion_seed import schedule_champion_seed_job

router = APIRouter(prefix="/reset", tags=["reset"])
logger = get_logger("league_api.reset")


@router.post(
    "/champions",
    response_model=ResetResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reset_champions() -> ResetResult:
    """Reset all champion records and schedule a reseed job.

    Returns:
        Reset result payload describing the scheduled job.
    """
    logger.info("reset_champions_requested")
    schedule_champion_seed_job(reason="reset_route", force_reset=True)
    return ResetResult(
        resource="champions",
        action="clear_and_reseed",
        status="scheduled",
        scheduled=True,
        message="Champion reset job scheduled.",
    )


@router.post(
    "/champions/{champ_id}",
    response_model=ResetResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reset_champion_by_id(champ_id: int) -> ResetResult:
    """Reset a single champion record by id.

    Args:
        champ_id: Numeric Riot champion identifier.

    Returns:
        Reset result payload describing the scheduled job.
    """
    logger.info("reset_champion_requested", extra={"champ_id": champ_id})
    schedule_champion_seed_job(reason="reset_route", champ_id=champ_id)
    return ResetResult(
        resource="champions",
        action="clear_and_reseed_one",
        status="scheduled",
        scheduled=True,
        message="Champion reset job scheduled.",
    )
