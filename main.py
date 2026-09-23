#Single entry for the Telegram bot and the web app
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import app_config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=app_config.log_level,
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

import jobs
import tg_bot
import web_api

STATIC_DIR = Path(__file__).resolve().parent / "static"


class RevalidatingStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    application = tg_bot.build_application()
    await application.initialize()
    await application.updater.start_polling(**tg_bot.POLLING_KWARGS)
    await application.start()
    background_tasks = jobs.start(application.bot)
    log.info("Telegram bot polling; web app ready")

    app.state.bot = application
    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        log.info("Telegram bot stopped")


app = FastAPI(title="Weather Assistant", lifespan=lifespan)
app.include_router(web_api.router)

app.mount("/", RevalidatingStaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=app_config.web["host"],
        port=app_config.web["port"],
        # NB! only one worker due to the TG bot
        workers=1,
    )
