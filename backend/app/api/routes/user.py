
from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.database.models import User
from app.schemas.user import UserProfileResponse

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/profile",
     response_model=UserProfileResponse,
     operation_id="get_my_profile"
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user
