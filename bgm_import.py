import os
import asyncio
from sqlalchemy import insert, select
from db import SessionLocal, Track  # async_session을 직접 import

async def seed_tracks():
    async with SessionLocal() as db:   # 비동기 세션 생성
        bgm_folder = os.path.join(os.path.dirname(__file__), "bgms")
        files = os.listdir(bgm_folder)

        for f in files:
            if f.endswith(".mp3") or f.endswith(".wav"):
                title = os.path.splitext(f)[0]
                file_url = f"/bgms/{f}"

                # 이미 같은 title이 있는지 확인
                result = await db.execute(
                    select(Track).where(Track.title == title)
                )
                existing = result.scalar_one_or_none()

                if existing is None:
                    stmt = insert(Track).values(title=title, file_url=file_url)
                    await db.execute(stmt)
                    print(f"Inserted: {title}")
                else:
                    print(f"Skipped (already exists): {title}")

        await db.commit()

if __name__ == "__main__":
    asyncio.run(seed_tracks())