#Single entry for the Telegram bot and the web app
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import app_config
import tg_bot
import web_api

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=app_config.log_level,
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot = tg_bot.build_application()

    # Same order as Application.run_polling: initialize, poll, then start the
    # update processor (which also starts the job queue and its daily jobs).
    await bot.initialize()
    await bot.updater.start_polling(**tg_bot.POLLING_KWARGS)
    await bot.start()
    log.info("Telegram bot polling; web app ready")

    app.state.bot = bot
    try:
        yield
    finally:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()
        log.info("Telegram bot stopped")


app = FastAPI(title="Weather Assistant", lifespan=lifespan)
app.include_router(web_api.router)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=app_config.web["host"],
        port=app_config.web["port"],
        # NB! only one worker due to the TG bot
        workers=1,
    )
