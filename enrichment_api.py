import os
from flask import Flask, request, jsonify
import logging

from database import Database

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] ENRICHMENT_API: %(message)s',
    handlers=[
        logging.FileHandler("enrichment_api.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EnrichmentAPI")

# Colors for terminal
C_MAGENTA = "\033[35m"
C_END = "\033[0m"

# Config (env overrides)
DB_PATH = os.getenv("DB_PATH", "bot.db")
API_KEY = os.getenv("ENRICH_API_KEY", "changeme")
API_HOST = os.getenv("ENRICH_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("ENRICH_API_PORT", "8001"))
MAX_LIMIT = 200

db = Database(DB_PATH)
app = Flask(__name__)


def require_api_key():
    key = request.headers.get("X-API-Key")
    if not key or key != API_KEY:
        return False
    return True


@app.before_request
def _auth():
    if not require_api_key():
        logger.warning(f"Unauthorized request from {request.remote_addr}")
        return jsonify({"error": "unauthorized"}), 401


@app.get("/market/unprocessed")
def get_unprocessed():
    logger.info(f"{C_MAGENTA}GET /market/unprocessed from {request.remote_addr}{C_END}")
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        logger.error(f"Invalid limit parameter: {request.args.get('limit')}")
        return jsonify({"error": "invalid limit"}), 400
    limit = max(1, min(limit, MAX_LIMIT))

    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        logger.error(f"Invalid offset parameter: {request.args.get('offset')}")
        return jsonify({"error": "invalid offset"}), 400
    offset = max(0, offset)

    rows = db.fetch_unenriched(limit=limit, offset=offset)
    logger.info(f"Returned {len(rows)} unenriched rows (limit={limit}, offset={offset})")
    return jsonify(rows)


@app.post("/market/<content_id>/enriched")
def post_enriched(content_id):
    logger.info(f"{C_MAGENTA}POST /market/{content_id}/enriched from {request.remote_addr}{C_END}")
    payload = request.get_json(silent=True)
    if payload is None:
        logger.error(f"Invalid JSON payload for {content_id}")
        return jsonify({"error": "invalid json"}), 400

    # Optionally ensure row exists and not enriched already
    existing = db.get_market_data_by_id(content_id)
    if not existing:
        logger.warning(f"Content {content_id} not found in MarketData")
        return jsonify({"error": "not found"}), 404
    if existing.get("enriched") == 1:
        logger.warning(f"Content {content_id} already enriched")
        return jsonify({"error": "already enriched"}), 409

    db.mark_enriched(content_id, request.data.decode("utf-8"))
    logger.info(f"Marked {content_id} as enriched")
    return jsonify({"status": "ok"})


def run():
    app.run(host=API_HOST, port=API_PORT)


if __name__ == "__main__":
    run()
