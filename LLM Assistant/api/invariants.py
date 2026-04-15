from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from auth.schemas import PublicUser
from invariants.schemas import ProjectInvariants
from invariants.service import load_project_invariants


router = APIRouter(prefix="/invariants", tags=["invariants"])


@router.get("/current", response_model=ProjectInvariants)
def get_current_invariants(_: PublicUser = Depends(get_current_user)) -> ProjectInvariants:
    return load_project_invariants()
