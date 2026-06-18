from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
import os

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("")
@router.get("/")
async def calendar_page():
    return FileResponse(os.path.join("templates", "calendar.html"))
